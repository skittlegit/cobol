"""Run a controlled Sol-primary or Luna-verifier T6 pass one item at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cobol_archaeologist.benchmark.t6_review import (
    BlindedReviewRecord,
    IndependentAttemptAudit,
    IndependentItemAudit,
    IndependentReviewRequestIdentity,
    IndependentVerifierAuditManifest,
    ReviewResponse,
    build_controlled_review_prompt,
)
from cobol_archaeologist.benchmark.t6_v2 import ArtifactPin, BlindedReviewItem
from cobol_archaeologist.eval.codex_batch import strict_codex_schema
from cobol_archaeologist.eval.codex_live import CodexTaskExecution
from cobol_archaeologist.eval.config3_live import (
    canonical_sha256,
    expected_codex_request_sha256,
    load_execution_bundle,
    persist_execution_bundle,
    runtime_source_sha256,
)

if __package__:
    from scripts.t6_review_coordinator import (
        CURRENT_NAME,
        DELIVERY_AUDIT_NAME,
        RESPONSES_NAME,
        CoordinatorState,
        _load_pinned_queue,
        record_response,
        release_next,
    )
else:
    from t6_review_coordinator import (  # type: ignore[import-not-found]
        CURRENT_NAME,
        DELIVERY_AUDIT_NAME,
        RESPONSES_NAME,
        CoordinatorState,
        _load_pinned_queue,
        record_response,
        release_next,
    )

MODEL_ID = "gpt-5.6-luna"
REASONING_EFFORT = "max"
REVIEWER_ROLE_PREFIX = "model_independent_verifier"
AI_PRIMARY_MODEL_ID = "gpt-5.6-sol"
AI_PRIMARY_ROLE_PREFIX = "model_ai_primary"
ControlledRole = Literal["ai_primary", "independent_verifier"]
ExecutionFunction = Callable[..., CodexTaskExecution]


class IndependentReviewRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_items: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    invalid_attempts: int = Field(ge=0)
    pending_review_item_id: str | None
    dry_run: bool
    audit_manifest: ArtifactPin | None


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _state(workspace: Path) -> CoordinatorState:
    return CoordinatorState.model_validate_json(
        (workspace / "coordinator-state.json").read_text(encoding="utf-8")
    )


def _active_item(workspace: Path) -> BlindedReviewItem:
    return BlindedReviewItem.model_validate_json(
        (workspace / CURRENT_NAME).read_text(encoding="utf-8")
    )


def _write_immutable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_text(encoding="utf-8") != text:
            raise RuntimeError(
                f"refusing to replace immutable audit artifact {path}"
            ) from None


def _identity_path(audit_dir: Path, item_id: str, attempt: int) -> Path:
    return audit_dir / "requests" / f"{item_id}-attempt-{attempt:03d}.json"


def _invalid_path(audit_dir: Path, item_id: str, attempt: int) -> Path:
    return audit_dir / "invalid" / f"{item_id}-attempt-{attempt:03d}.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(root: Path, path: Path) -> ArtifactPin:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(
            "independent audit artifacts must remain inside repository root"
        )
    return ArtifactPin(
        path=resolved.relative_to(resolved_root).as_posix(), sha256=_sha(resolved)
    )


def _reviewer_pseudonym(
    state: CoordinatorState, *, review_role: ControlledRole = "independent_verifier"
) -> str:
    prefix = (
        AI_PRIMARY_ROLE_PREFIX if review_role == "ai_primary" else REVIEWER_ROLE_PREFIX
    )
    if not state.reviewer_pseudonym.startswith(prefix):
        raise ValueError(f"controlled runner requires a {prefix} pseudonym")
    if state.review_role != review_role:
        raise ValueError(f"coordinator workspace is not a {review_role} pass")
    return state.reviewer_pseudonym


def _request_identity(
    *,
    item: BlindedReviewItem,
    state: CoordinatorState,
    attempt: int,
    prompt: str,
    schema: dict,
    transport: Literal["wsl", "native"],
    codex_binary: str,
    runtime_sha256: str,
    account_sha256: str,
    review_role: ControlledRole = "independent_verifier",
) -> IndependentReviewRequestIdentity:
    model_id = AI_PRIMARY_MODEL_ID if review_role == "ai_primary" else MODEL_ID
    request_hash = expected_codex_request_sha256(
        prompt=prompt,
        schema=schema,
        sources={},
        transport=transport,
        codex_binary=codex_binary,
        runtime_source_sha256=runtime_sha256,
        chatgpt_account_sha256=account_sha256,
        authorized_hunts=(),
    )
    return IndependentReviewRequestIdentity(
        schema_version="1",
        review_role=review_role,
        review_item_id=item.review_item_id,
        release_ordinal=item.release_ordinal,
        attempt=attempt,
        source_alias=item.source_alias,
        source_text_sha256=_sha_text(item.source_text),
        authority_sha256=canonical_sha256(item.authority),
        packet=state.packet,
        release_policy=state.release_policy,
        provider="chatgpt-codex",
        authentication="ChatGPT",
        authentication_identity_sha256=account_sha256,
        model_id=model_id,
        reasoning_effort=REASONING_EFFORT,
        transport=transport,
        codex_binary=codex_binary,
        prompt_sha256=_sha_text(prompt),
        schema_sha256=canonical_sha256(schema),
        runtime_source_sha256=runtime_sha256,
        expected_request_sha256=request_hash,
        visible_review_items=1,
        staged_source_bundles=0,
        tools_authorized=0,
        prior_item_context_included=False,
    )


def _select_execution(
    transport: Literal["wsl", "native"],
) -> ExecutionFunction:
    if transport == "native":
        from cobol_archaeologist.eval.codex_native import execute_codex_task_native

        return execute_codex_task_native
    from cobol_archaeologist.eval.codex_live import execute_codex_task

    return execute_codex_task


def _verify_chatgpt_account(
    *, transport: Literal["wsl", "native"], codex_binary: str, distro: str
) -> str:
    if transport == "native":
        from cobol_archaeologist.eval.codex_native import (
            native_chatgpt_account_sha256,
            native_login_status,
        )

        native_login_status(codex_binary)
        return native_chatgpt_account_sha256()
    from cobol_archaeologist.eval.codex_live import (
        _check_chatgpt_login,
        _wsl_chatgpt_account_sha256,
    )

    _check_chatgpt_login(codex_binary=codex_binary, distro=distro)
    return _wsl_chatgpt_account_sha256(distro=distro)


def _record_model_response(
    *,
    root: Path,
    workspace: Path,
    state: CoordinatorState,
    item: BlindedReviewItem,
    response: ReviewResponse,
    now: Callable[[], datetime],
    review_role: ControlledRole = "independent_verifier",
) -> None:
    completed_at = now().astimezone(UTC).isoformat().replace("+00:00", "Z")
    record = BlindedReviewRecord(
        review_item_id=item.review_item_id,
        reviewer_pseudonym=_reviewer_pseudonym(state, review_role=review_role),
        completed_at=completed_at,
        review_response=response,
    )
    temporary = workspace / ".independent-response.json"
    temporary.write_text(record.model_dump_json(), encoding="utf-8")
    try:
        record_response(root=root, workspace=workspace, response_path=temporary)
    finally:
        temporary.unlink(missing_ok=True)


def finalize_independent_audit(
    *,
    root: Path,
    workspace: Path,
    audit_dir: Path,
    manifest_path: Path,
    chatgpt_account_sha256: str,
    review_role: ControlledRole = "independent_verifier",
) -> ArtifactPin:
    """Freeze and reconcile all 22 isolated request/bundle retry chains."""

    state = _state(workspace)
    _reviewer_pseudonym(state, review_role=review_role)
    if state.current_item_id is not None or state.next_ordinal != 23:
        raise ValueError("aggregate verifier audit requires 22 completed items")
    responses_path = workspace / RESPONSES_NAME
    delivery_path = workspace / DELIVERY_AUDIT_NAME
    responses = [
        BlindedReviewRecord.model_validate_json(raw)
        for raw in responses_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]
    queue = sorted(
        _load_pinned_queue(root=root, state=state),
        key=lambda item: item.release_ordinal,
    )
    if [row.review_item_id for row in responses] != [
        item.review_item_id for item in queue
    ]:
        raise ValueError("verifier responses differ from release queue order")
    audited_items: list[IndependentItemAudit] = []
    expected_identity_paths: set[Path] = set()
    expected_invalid_paths: set[Path] = set()
    expected_raw_dirs: set[Path] = set()
    for item, response in zip(queue, responses, strict=True):
        attempts: list[IndependentAttemptAudit] = []
        for attempt_number in range(1, 1000):
            identity_path = _identity_path(
                audit_dir, item.review_item_id, attempt_number
            )
            if not identity_path.is_file():
                break
            identity = IndependentReviewRequestIdentity.model_validate_json(
                identity_path.read_text(encoding="utf-8")
            )
            expected_identity_paths.add(identity_path.resolve())
            if (
                identity.review_role != review_role
                or identity.review_item_id != item.review_item_id
                or identity.release_ordinal != item.release_ordinal
                or identity.attempt != attempt_number
                or identity.authentication_identity_sha256 != chatgpt_account_sha256
                or identity.model_id
                != (AI_PRIMARY_MODEL_ID if review_role == "ai_primary" else MODEL_ID)
            ):
                raise ValueError("request identity differs from aggregate audit")
            bundle = load_execution_bundle(
                artifact_dir=audit_dir,
                key=identity.expected_request_sha256,
                expected_request_sha256=identity.expected_request_sha256,
            )
            if bundle is None:
                raise ValueError("request identity has no complete raw bundle")
            execution_path = (
                audit_dir / "raw" / identity.expected_request_sha256 / "execution.json"
            )
            marker_path = (
                audit_dir / "raw" / identity.expected_request_sha256 / "complete"
            )
            expected_raw_dirs.add(execution_path.parent.resolve())
            invalid_path = _invalid_path(audit_dir, item.review_item_id, attempt_number)
            invalid = invalid_path.is_file()
            if invalid:
                expected_invalid_paths.add(invalid_path.resolve())
                try:
                    ReviewResponse.model_validate_json(bundle.final_message)
                except ValueError:
                    pass
                else:
                    raise ValueError("invalid marker accompanies a valid response")
            else:
                parsed = ReviewResponse.model_validate_json(bundle.final_message)
                if parsed != response.review_response:
                    raise ValueError(
                        "accepted raw response differs from response JSONL"
                    )
            attempts.append(
                IndependentAttemptAudit(
                    attempt=attempt_number,
                    request_identity=_pin(root, identity_path),
                    raw_execution=_pin(root, execution_path),
                    raw_completion_marker=_pin(root, marker_path),
                    expected_request_sha256=identity.expected_request_sha256,
                    outcome="schema_invalid" if invalid else "accepted",
                    invalid_marker=_pin(root, invalid_path) if invalid else None,
                )
            )
            if not invalid:
                break
        if not attempts or attempts[-1].outcome != "accepted":
            raise ValueError("each verifier item needs a terminal accepted attempt")
        audited_items.append(
            IndependentItemAudit(
                release_ordinal=item.release_ordinal,
                review_item_id=item.review_item_id,
                attempts=attempts,
            )
        )
    actual_identity_paths = {
        path.resolve() for path in (audit_dir / "requests").glob("*.json")
    }
    actual_invalid_paths = {
        path.resolve() for path in (audit_dir / "invalid").glob("*.json")
    }
    raw_root = audit_dir / "raw"
    actual_raw_dirs = (
        {path.resolve() for path in raw_root.iterdir() if path.is_dir()}
        if raw_root.is_dir()
        else set()
    )
    if (
        actual_identity_paths != expected_identity_paths
        or actual_invalid_paths != expected_invalid_paths
        or actual_raw_dirs != expected_raw_dirs
    ):
        raise ValueError(
            "audit directory contains orphan, gapped, or post-accepted attempts"
        )
    if any(
        {path.name for path in raw_dir.iterdir()} != {"execution.json", "complete"}
        for raw_dir in actual_raw_dirs
    ):
        raise ValueError("raw audit bundle contains unexpected artifacts")
    audit = IndependentVerifierAuditManifest(
        schema_version="1",
        finalized=True,
        review_role=review_role,
        reviewer_pseudonym=state.reviewer_pseudonym,
        packet=state.packet,
        release_policy=state.release_policy,
        responses=_pin(root, responses_path),
        sequential_delivery_audit=_pin(root, delivery_path),
        provider="chatgpt-codex",
        authentication="ChatGPT",
        authentication_identity_sha256=chatgpt_account_sha256,
        model_id=(AI_PRIMARY_MODEL_ID if review_role == "ai_primary" else MODEL_ID),
        reasoning_effort=REASONING_EFFORT,
        visible_review_items_per_call=1,
        staged_source_bundles_per_call=0,
        tools_authorized_per_call=0,
        prior_item_context_included=False,
        item_count=22,
        release_ordinal_order=list(range(1, 23)),
        review_item_order=[item.review_item_id for item in queue],
        items=audited_items,
    )
    _write_immutable(manifest_path, audit.model_dump_json(indent=2) + "\n")
    return _pin(root, manifest_path)


def run_independent_review(
    *,
    root: Path,
    workspace: Path,
    audit_dir: Path,
    transport: Literal["wsl", "native"],
    codex_binary: str,
    distro: str,
    chatgpt_account_sha256: str,
    runtime_sha256: str,
    timeout_s: float = 1200,
    max_items: int = 22,
    max_attempts_per_item: int = 3,
    dry_run: bool = False,
    execution_function: ExecutionFunction | None = None,
    account_verifier: Callable[[], str] | None = None,
    support_runtime_preparer: Callable[..., str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    aggregate_manifest_path: Path | None = None,
    review_role: ControlledRole = "independent_verifier",
) -> IndependentReviewRunSummary:
    """Run or resume the isolated verifier pass without sharing item history."""

    resolved_workspace = workspace.resolve()
    resolved_audit = audit_dir.resolve()
    if (
        resolved_audit == resolved_workspace
        or resolved_audit.is_relative_to(resolved_workspace)
        or resolved_workspace.is_relative_to(resolved_audit)
    ):
        raise ValueError("private audit_dir and reviewer workspace must be separate")
    state = _state(workspace)
    _reviewer_pseudonym(state, review_role=review_role)
    if not dry_run:
        verifier = account_verifier or (
            lambda: _verify_chatgpt_account(
                transport=transport, codex_binary=codex_binary, distro=distro
            )
        )
        if verifier() != chatgpt_account_sha256:
            raise RuntimeError("active ChatGPT account differs from frozen identity")
    selected_execution = execution_function or _select_execution(transport)
    if transport == "wsl":
        if support_runtime_preparer is None:
            from cobol_archaeologist.eval.codex_live import prepare_support_runtime

            support_runtime_preparer = prepare_support_runtime
        support_root = support_runtime_preparer(commit=runtime_sha256, distro=distro)
    else:
        support_root = str(root.resolve())
    schema = strict_codex_schema(ReviewResponse)
    completed = 0
    provider_calls = 0
    invalid_attempts = 0

    while completed < max_items:
        state = _state(workspace)
        if state.finalized or state.next_ordinal > 22:
            break
        if state.current_item_id is None:
            release_next(root=root, workspace=workspace)
            state = _state(workspace)
        item = _active_item(workspace)
        if state.current_item_id != item.review_item_id:
            raise RuntimeError("coordinator state differs from active envelope")

        recorded = False
        for attempt in range(1, max_attempts_per_item + 1):
            prompt = build_controlled_review_prompt(
                item, attempt=attempt, review_role=review_role
            )
            identity = _request_identity(
                item=item,
                state=state,
                attempt=attempt,
                prompt=prompt,
                schema=schema,
                transport=transport,
                codex_binary=codex_binary,
                runtime_sha256=runtime_sha256,
                account_sha256=chatgpt_account_sha256,
                review_role=review_role,
            )
            identity_path = _identity_path(audit_dir, item.review_item_id, attempt)
            _write_immutable(identity_path, identity.model_dump_json(indent=2))
            bundle = load_execution_bundle(
                artifact_dir=audit_dir,
                key=identity.expected_request_sha256,
                expected_request_sha256=identity.expected_request_sha256,
            )
            if bundle is None:
                if dry_run:
                    return IndependentReviewRunSummary(
                        completed_items=completed,
                        provider_calls=0,
                        invalid_attempts=invalid_attempts,
                        pending_review_item_id=item.review_item_id,
                        dry_run=True,
                        audit_manifest=None,
                    )
                if verifier() != chatgpt_account_sha256:
                    raise RuntimeError(
                        "active ChatGPT account differs from frozen identity"
                    )
                bundle = selected_execution(
                    prompt=prompt,
                    schema=schema,
                    sources={},
                    support_root=support_root,
                    distro=distro,
                    codex_binary=codex_binary,
                    model_id=(
                        AI_PRIMARY_MODEL_ID if review_role == "ai_primary" else MODEL_ID
                    ),
                    reasoning_effort=REASONING_EFFORT,
                    timeout_s=timeout_s,
                    runtime_source_sha256=runtime_sha256,
                    authentication_identity_sha256=chatgpt_account_sha256,
                    authorized_hunts=(),
                )
                provider_calls += 1
                if bundle.tool_logs:
                    raise RuntimeError("independent review task attempted a tool call")
                persist_execution_bundle(
                    bundle,
                    artifact_dir=audit_dir,
                    key=identity.expected_request_sha256,
                    expected_request_sha256=identity.expected_request_sha256,
                )
            if bundle.tool_logs:
                raise RuntimeError("independent review raw bundle contains tool calls")
            try:
                response = ReviewResponse.model_validate_json(bundle.final_message)
            except ValueError as exc:
                invalid_attempts += 1
                invalid = {
                    "schema_version": "1",
                    "request_sha256": identity.expected_request_sha256,
                    "error_sha256": _sha_text(str(exc)),
                }
                _write_immutable(
                    _invalid_path(audit_dir, item.review_item_id, attempt),
                    json.dumps(invalid, sort_keys=True, separators=(",", ":")),
                )
                continue
            _record_model_response(
                root=root,
                workspace=workspace,
                state=state,
                item=item,
                response=response,
                now=now,
                review_role=review_role,
            )
            completed += 1
            recorded = True
            break
        if not recorded:
            raise RuntimeError(
                f"independent review exhausted {max_attempts_per_item} fresh tasks "
                f"for {item.review_item_id}"
            )

    final_state = _state(workspace)
    pending = final_state.current_item_id
    audit_manifest = None
    if not dry_run and final_state.next_ordinal == 23 and pending is None:
        audit_manifest = finalize_independent_audit(
            root=root,
            workspace=workspace,
            audit_dir=audit_dir,
            manifest_path=(
                aggregate_manifest_path
                or audit_dir / f"{review_role.replace('_', '-')}-audit-manifest.json"
            ),
            chatgpt_account_sha256=chatgpt_account_sha256,
            review_role=review_role,
        )
    return IndependentReviewRunSummary(
        completed_items=completed,
        provider_calls=provider_calls,
        invalid_attempts=invalid_attempts,
        pending_review_item_id=pending,
        dry_run=dry_run,
        audit_manifest=audit_manifest,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--transport", choices=("native", "wsl"), required=True)
    parser.add_argument("--codex-binary", required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--chatgpt-account-sha256", required=True)
    parser.add_argument("--runtime-source-sha256")
    parser.add_argument("--timeout-s", type=float, default=1200)
    parser.add_argument("--max-items", type=int, default=22)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--review-role",
        choices=("ai_primary", "independent_verifier"),
        default="independent_verifier",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    root = args.root.resolve()
    summary = run_independent_review(
        root=root,
        workspace=args.workspace,
        audit_dir=args.audit_dir,
        transport=args.transport,
        codex_binary=args.codex_binary,
        distro=args.distro,
        chatgpt_account_sha256=args.chatgpt_account_sha256,
        runtime_sha256=args.runtime_source_sha256 or runtime_source_sha256(root),
        timeout_s=args.timeout_s,
        max_items=args.max_items,
        dry_run=args.dry_run,
        review_role=args.review_role,
    )
    print(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

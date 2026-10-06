"""Additive Linux GnuCOBOL backend; no Windows policy or frozen-source changes.

WSL is a distinct validation environment, not evidence of Windows execution.
Fixtures retain RealValidationBackend's finite proof scope and original staging.
The runner receives code and base64 source through JSON on stdin, never a shell.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from cobol_archaeologist.migration import backend as native_backend
from cobol_archaeologist.migration.backend import (
    _PROCEDURE,
    FixtureProtocol,
    RealValidationBackend,
    _digest,
)
from cobol_archaeologist.migration.contracts import ValidationCapability
from cobol_archaeologist.migration.validate import CheckStatus
from cobol_archaeologist.model.run_cobol import (
    CompileResult,
    _parse_messages,
    _validate_input_names,
)
from cobol_archaeologist.parser.paragraphs import parse_program
from cobol_archaeologist.tool_types import RunInputs, RunResult

BOOTSTRAP = "import json,sys; p=json.load(sys.stdin); exec(compile(p['runner'],'<pinned-wsl-runner>','exec'), {'REQUEST':p['request']})"
RUNNER = r'''
import base64, hashlib, json, os, pathlib, re, shutil, signal, subprocess, sys, tempfile
ENV = {'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8', 'LC_ALL':'C.UTF-8'}
COBC = '/usr/bin/cobc'
CAP = 65536
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def identity():
    if not re.search(r'^ID=ubuntu$', pathlib.Path('/etc/os-release').read_text(), re.MULTILINE):
        raise RuntimeError('Pinned Ubuntu distribution identity is unsupported')
    binary = pathlib.Path(COBC).resolve(strict=True)
    version = subprocess.run([COBC,'--version'], env=ENV, capture_output=True, timeout=20, check=True).stdout.decode()
    if not re.search(r'cobc \(GnuCOBOL\) 3\.2\.0\b', version):
        raise RuntimeError('Unsupported Linux GnuCOBOL: ' + version)
    dependencies = {}
    tools = [COBC, '/usr/bin/python3', '/usr/bin/gcc', '/usr/bin/as', '/usr/bin/ld']
    # Pin the C compiler proper as well as the linker/compiler launchers.
    cc1 = subprocess.run(['/usr/bin/gcc','-print-prog-name=cc1'], env=ENV, capture_output=True, timeout=20, check=True).stdout.decode().strip()
    tools.append(cc1)
    native_tools = {}
    for tool in tools:
        path = pathlib.Path(tool).resolve(strict=True)
        native_tools[str(path)] = sha(path)
        proc = subprocess.run(['/usr/bin/ldd',str(path)], env=ENV, capture_output=True, timeout=20)
        output = proc.stdout.decode() + proc.stderr.decode()
        if 'not found' in output:
            raise RuntimeError('Missing native dependency: ' + output)
        for match in re.findall(r'(?:=>\s*)?(/[^\s()]+)', output):
            dependency = pathlib.Path(match).resolve(strict=True)
            dependencies[str(dependency)] = sha(dependency)
    configuration = {}
    for directory in ['/usr/share/gnucobol/config','/usr/share/gnucobol/copy']:
        for path in sorted(pathlib.Path(directory).rglob('*')):
            if path.is_file():
                configuration[str(path.resolve())] = sha(path)
    return {'platform':'linux-wsl', 'binary':COBC, 'native_binary':str(binary),
            'binary_sha256':sha(COBC), 'native_binary_sha256':sha(binary),
            'version':version, 'banner':version, 'python_version':sys.version,
            'native_tools':native_tools, 'dependencies':dependencies,
            'configuration':configuration, 'environment':ENV,
            'os_release_sha256':sha('/etc/os-release')}
def cap(data):
    suffix = '\n...[truncated at 65536 bytes]' if len(data)>CAP else ''
    return data[:CAP].decode('utf-8',errors='replace') + suffix
def invoke(args, root, stdin=b'', timeout=20):
    # File captures keep an overflowing child out of the host's memory.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(args, cwd=root, env=ENV, stdin=subprocess.PIPE,
            stdout=out, stderr=err, start_new_session=True)
        timed_out = False
        try:
            process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        out.seek(0); err.seek(0)
        return process.returncode, cap(out.read(CAP+1)), cap(err.read(CAP+1)), timed_out
def execute():
    current = identity()
    if REQUEST['operation']=='identity':
        return {'identity':current}
    if REQUEST.get('identity') != current:
        raise RuntimeError('Linux compiler/dependency identity changed after backend construction')
    root = pathlib.Path(tempfile.mkdtemp(prefix='migration_wsl_',dir='/tmp')).resolve()
    if root.parent != pathlib.Path('/tmp').resolve() or not root.name.startswith('migration_wsl_'):
        raise RuntimeError('Unverified Linux staging target')
    try:
        source = base64.b64decode(REQUEST['source_base64'],validate=True)
        (root/'prog.cbl').write_bytes(source)
        for name, text in REQUEST.get('files',{}).items():
            parts = name.split('/')
            if not name or any(p in ('','.','..') for p in parts) or '\\' in name or ':' in name or '\x00' in name or name.casefold() in ('prog','prog.cbl','prog.exe'):
                raise ValueError('Unsafe runner input file')
            target = (root/name).resolve()
            if not target.is_relative_to(root):
                raise ValueError('Runner input escapes staging')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(base64.b64decode(text,validate=True))
        syntax = REQUEST['operation']=='compile'
        args = [COBC,'-fsyntax-only','-std=ibm','prog.cbl'] if syntax else [COBC,'-x','-std=ibm','-I','.','-o','prog','prog.cbl']
        code,out,err,timed_out = invoke(args,root)
        diagnostics = (err+out).replace(str(root)+'/', '').replace(str(root),'')
        if timed_out:
            raise RuntimeError('Linux compilation timed out after 20 seconds: '+diagnostics)
        if syntax:
            return {'ok':code==0,'output':diagnostics,'compile_exit_code':code}
        if code != 0 or not (root/'prog').is_file():
            return {'compiled_ok':False,'stderr':diagnostics,'compile_exit_code':code}
        code,out,err,timed_out = invoke([str(root/'prog')],root,
            base64.b64decode(REQUEST['stdin_base64'],validate=True),timeout=5)
        return {'compiled_ok':True,'stdout':out,'stderr':err,
                'exit_code':None if timed_out else code,'timed_out':timed_out,
                'compile_exit_code':0}
    finally:
        # Only the exact verified Linux-created directory is removed.
        if root.parent == pathlib.Path('/tmp').resolve() and root.name.startswith('migration_wsl_'):
            shutil.rmtree(root)
try:
    print(json.dumps({'result':execute()},sort_keys=True))
except Exception as exc:
    print(json.dumps({'error':type(exc).__name__+': '+str(exc)}))
'''


class WSLValidationBackend(RealValidationBackend):
    """Pin Linux compiler dependencies independently of the native backend."""

    def __init__(self, fixtures, *, distro="Ubuntu", wsl_binary=None):
        self.fixtures = FixtureProtocol.model_validate(fixtures.model_dump(mode="json"))
        self.distro = distro
        self.wsl_binary = wsl_binary or shutil.which("wsl.exe")
        self._compiler_error = None
        self.compiler = None
        self._transport_pin = None
        self._execution_code_pin = self._code_identity()
        try:
            if distro != "Ubuntu" or not self.wsl_binary:
                raise RuntimeError("Pinned Ubuntu WSL transport is unavailable or unsupported")
            path = Path(self.wsl_binary).resolve(strict=True)
            self.wsl_binary = str(path)
            self._transport_pin = hashlib.sha256(path.read_bytes()).hexdigest()
            self.compiler = self._request({"operation": "identity"})["identity"]
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self._compiler_error = str(exc)

    def _request(self, request):
        if self._execution_code_pin != self._code_identity():
            raise RuntimeError("Pinned WSL runner/backend source changed after construction")
        if not self.wsl_binary or self._transport_pin != hashlib.sha256(Path(self.wsl_binary).read_bytes()).hexdigest():
            raise RuntimeError("Pinned WSL transport unavailable or changed")
        payload = json.dumps({"runner": RUNNER, "request": request}).encode()
        process = subprocess.run([self.wsl_binary, "-d", self.distro, "--", "/usr/bin/python3", "-c", BOOTSTRAP],
                                 input=payload, capture_output=True, timeout=90, check=False)
        if process.returncode:
            raise RuntimeError("WSL runner unavailable: " + process.stderr.decode("utf-8", errors="replace")[:65536])
        try:
            result = json.loads(process.stdout)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("WSL runner did not return valid JSON") from exc
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    def _code_identity(self):
        return (hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                hashlib.sha256(RUNNER.encode()).hexdigest(), hashlib.sha256(BOOTSTRAP.encode()).hexdigest())

    @property
    def identity_sha256(self):
        return _digest({"base_backend_identity_sha256": super().identity_sha256,
                        "wsl_backend_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "runner_sha256": hashlib.sha256(RUNNER.encode()).hexdigest(),
                        "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
                        "wsl_binary": self.wsl_binary, "wsl_binary_sha256": self._transport_pin,
                        "distro": self.distro, "compiler": self.compiler})

    def capability_receipt(self):
        result = super().capability_receipt()
        modules = {Path(native_backend.__file__), Path(__file__)}
        for function in (native_backend.preprocess, native_backend.get_language,
                         native_backend.expand, native_backend.parse_program,
                         native_backend.build_call_graph, native_backend.compile_check,
                         native_backend.trace_variable, native_backend.slice_on,
                         _validate_input_names):
            modules.add(Path(function.__code__.co_filename))
        repo = Path(__file__).resolve().parents[1]
        sources = {(p.resolve().relative_to(repo).as_posix() if p.resolve().is_relative_to(repo) else str(p.resolve())):
                   hashlib.sha256(p.read_bytes()).hexdigest() for p in modules}
        result.update(schema_version="migration-wsl-backend-capability-v1", execution_environment="linux-wsl",
                      wsl_distro=self.distro, wsl_binary=self.wsl_binary, wsl_binary_sha256=self._transport_pin,
                      runner_sha256=hashlib.sha256(RUNNER.encode()).hexdigest(),
                      bootstrap_sha256=hashlib.sha256(BOOTSTRAP.encode()).hexdigest(),
                      backend_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      source_dependency_sha256=sources,
                      windows_execution_claim=False)
        return result

    def _compiler_pin(self):
        if self.compiler is None:
            raise RuntimeError(self._compiler_error or "Pinned Linux compiler unavailable")
        if self._request({"operation": "identity"})["identity"] != self.compiler:
            raise RuntimeError("Linux compiler/dependency identity changed after backend construction")

    def _execute(self, source, inputs=None, *, syntax=False):
        if self.compiler is None:
            raise RuntimeError(self._compiler_error or "Pinned Linux compiler unavailable")
        inputs = inputs or RunInputs()
        names = _validate_input_names(inputs.files)
        return self._request({"operation": "compile" if syntax else "run", "identity": self.compiler,
            "source_base64": base64.b64encode(source.encode()).decode(),
            "stdin_base64": base64.b64encode(inputs.stdin.encode()).decode(),
            "files": {names[n]: base64.b64encode(t.encode()).decode() for n,t in inputs.files.items()}})

    def run_source(self, source, inputs=None):
        result = self._execute(source, inputs)
        return RunResult.model_validate({k:v for k,v in result.items() if k != "compile_exit_code"})

    def compile(self, case, files, *, host=None):
        if case.validation_capability not in (ValidationCapability.BATCH_EXECUTABLE, ValidationCapability.COPYBOOK_FANOUT):
            return self._obs("compile", CheckStatus.UNAVAILABLE, error="No executable CICS capability")
        try:
            with self._stage(case, files) as root:
                source = self._expanded(root, files, host or case.primary_program)
                result = self._execute(source, syntax=True)
                compiled = CompileResult(ok=result["ok"], messages=_parse_messages(result["output"]))
                return self._obs("compile", CheckStatus.PASS if compiled.ok else CheckStatus.FAIL,
                    host=host or case.primary_program, compile_result=compiled.model_dump(),
                    compile_exit_code=result["compile_exit_code"], compiler_output=result["output"],
                    expanded_source_sha256=hashlib.sha256(source.encode()).hexdigest())
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return self._obs("compile", CheckStatus.UNAVAILABLE, error=str(exc))

    def behavior(self, case, files, check):
        fixtures = self.fixtures.checks.get(check.check_id, ())
        if (case.validation_capability not in (ValidationCapability.BATCH_EXECUTABLE, ValidationCapability.COPYBOOK_FANOUT)
                or not fixtures or self.compiler is None):
            return self._obs(check.check_id, CheckStatus.UNAVAILABLE,
                             error=self._compiler_error or "No pinned executable fixtures/capability")
        try:
            with self._stage(case, files) as root:
                normalized = lambda value: Path(value).stem.upper()
                if (case.validation_capability == ValidationCapability.COPYBOOK_FANOUT and
                    {normalized(f.host) for f in fixtures} != {normalized(h) for h in case.affected_hosts}):
                    raise ValueError("fixture check does not cover exactly the required host fan-out")
                results = []
                for fixture in fixtures:
                    original = self._expanded(root, files, fixture.host)
                    program = parse_program(self._path(root, files, fixture.host), include_preamble=True)
                    known = {p.span.name for p in program.paragraphs}
                    if not set(fixture.perform) <= known:
                        raise ValueError("fixture performs an absent paragraph")
                    source = original
                    if not fixture.run_original_main:
                        headers = list(_PROCEDURE.finditer(original))
                        if len(headers) != 1:
                            raise ValueError("fixture requires one plain PROCEDURE DIVISION (no USING)")
                        driver = "\n" + "\n".join("           " + statement for statement in (
                            *fixture.initialize, *("PERFORM " + p for p in fixture.perform),
                            *("DISPLAY " + name for name in fixture.observe), "STOP RUN.")) + "\n"
                        position = headers[0].end()
                        source = original[:position] + driver + original[position:]
                    raw = self._execute(source, RunInputs(stdin=fixture.stdin))
                    result = RunResult.model_validate({k:v for k,v in raw.items() if k != "compile_exit_code"})
                    actual = result.stdout.replace("\r\n", "\n")
                    expected = fixture.expected_stdout.replace("\r\n", "\n")
                    passed = result.compiled_ok and result.exit_code == 0 and not result.timed_out and actual == expected
                    results.append({"fixture_id":fixture.fixture_id, "host":fixture.host, "passed":passed,
                        "actual_stdout":actual, "expected_stdout":expected,
                        "expanded_original_source_sha256":hashlib.sha256(original.encode()).hexdigest(),
                        "instrumented_source_sha256":hashlib.sha256(source.encode()).hexdigest(),
                        "source_bundle_sha256":_digest({n:hashlib.sha256(t.encode()).hexdigest() for n,t in files.items()}),
                        "compile_exit_code":raw["compile_exit_code"], "run_result":result.model_dump(mode="json")})
                return self._obs(check.check_id, CheckStatus.PASS if all(r["passed"] for r in results) else CheckStatus.FAIL,
                                 fixtures=results)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return self._obs(check.check_id, CheckStatus.UNAVAILABLE, error=str(exc))

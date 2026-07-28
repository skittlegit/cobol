# Repository rulesets

The JSON files in this directory are the version-controlled source for the
live GitHub repository rulesets.

Installed on 2026-07-27:

- `protect-default.json` → repository ruleset `19797263`
- `protect-track-branches.json` → repository ruleset `19797264`

Both rulesets were read back as `active` after installation. Verify the live
state with:

```console
gh api repos/skittlegit/cobol/rulesets
```

The default-branch ruleset requires changes to arrive through a pull request
and requires all review threads to be resolved, but it does not require an
approving review. This permits the repository owner to merge their own pull
request while still preserving the review discussion and merge-commit policy.

Changing these files does not update GitHub automatically. Apply any later
change through the repository-rulesets API and record the resulting state here
in the same reviewed commit.

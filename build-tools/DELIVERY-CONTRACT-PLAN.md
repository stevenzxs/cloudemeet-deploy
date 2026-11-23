# Online/offline delivery contract implementation

Approved design (2026-11-23): the user separately confirmed the proposed standard
change, then required scripts first, knowledgebase second. No dispatch, allocation,
publication, SSH, installation or deployment is authorized by this maintenance task.

1. Add failing regressions for instance/project ownership, all-client publication
   gating, online pull and offline load selection, and deployment parameter prompts.
2. Parameterize the existing updater, retain image-only compatibility refusal,
   preserve state and roll back by old image ID. Reuse it for offline upgrades.
3. Add registry identity helpers shared by initial installation, updates and
   offline export. Reuse the existing first-install core and scoped certificate checks.
4. Gate joint publication on both reusable build workflows. Publish clients and
   matching deployment material as one immutable Release after exact image publication.
5. Add an explicit deployment-choice planner (no implicit SSH/apply); missing
   first/upgrade, target server and origin are prompts, existing values are reused.
6. Update project instructions, Skill, input hashes and operation examples; execute
   no-Docker regressions and review the complete diff, then close config main branch.
7. Only then update knowledgebase contract, templates and unique audit ledger,
   recording local evidence separately from unexecuted Actions/target acceptance.

Validation: Python unit tests with mocked host commands, Node client tests, Bash
syntax, YAML structure/permissions, layout/governance and input hash checks.
No local product build or real Docker operations. New runtime behavior remains
pending a separately authorized Actions/target acceptance. Historical r14 bytes
and Run remain unchanged; do not create a new rN to deploy existing publication.

Resume contract: plan_first; implement and verify configuration, close config main,
then synchronize knowledgebase and its main. Stop for concurrency conflicts,
failed gates, missing authorization or any requested server/build activity.
Checkpoint: runtime/archive/Release transformations and refused-error regressions
are implemented, including final inventory refresh and registry/material image
binding. Fresh local verification on 2026-11-23: Python 142/142 (20.787s), Node
49/49, governance 3/3, layout, 101 input hashes, Bash syntax and five workflow YAML
parses passed. All workflow triggers are manual/reusable, not push-triggered.
Diff and limited secret-pattern scan are final submission gates. No actionlint or
gitleaks is installed locally; syntax/pattern checks are not their equivalents.

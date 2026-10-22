# OSWALD Section 2: Implementation Plan
## Isolation & Execution Model — Git Worktree + Docker Sandbox

## Objective

Implement an isolation and execution model that gives each OSWALD task its own Git workspace and restricted Docker environment. This allows agents to modify and test code without directly sharing working directories or freely accessing the host machine.

## Implementation Order

### Step 1: Build the Git Worktree Manager

**Goal:** Create an independent working directory and branch for each task.

**Tasks:**
- Create a task-specific Git worktree under `/tmp`.
- Assign a task-specific branch, such as `oswald/task-<task_id>`.
- Track the worktree path and branch against the task ID.
- Provide operations to create, inspect, and clean up worktrees.
- Handle setup failures without leaving partially created worktrees behind.

**Acceptance checks:**
- Two tasks can create separate worktrees from the same repository.
- Editing a tracked file in one worktree does not change the working file in the other worktree.
- Each task is associated with the correct branch and path.
- Cleanup removes the task worktree when it is safe to do so.

### Step 2: Build the Docker Sandbox Manager

**Goal:** Start and manage a restricted container for a task.

**Tasks:**
- Create a task-specific container.
- Run the container as a non-root user.
- Disable container networking with `--network none`.
- Use a read-only root filesystem where compatible with the runtime.
- Configure a writable temporary directory, such as `/tmp`, with appropriate restrictions.
- Set resource limits, including 2 GB memory and 2 CPUs.
- Drop Linux capabilities with `--cap-drop ALL`.
- Mount only the task workspace required for execution.
- Provide operations to start, inspect, stop, and remove containers.

**Acceptance checks:**
- The container starts with the intended security and resource settings.
- The process runs as a non-root user.
- Container networking is disabled.
- The container can be stopped and removed reliably.
- Failures are reported clearly and do not leave unmanaged containers behind.

**Implementation note:** A read-only root filesystem means tools may need writable mounts for temporary files, caches, or test outputs. Configure only the writable paths required by the chosen toolchain.

### Step 3: Connect the Worktree to Docker

**Goal:** Ensure each container operates on the correct task-specific Git worktree.

**Tasks:**
- Bind-mount the task worktree into the container at `/workspace`.
- Set `/workspace` as the container working directory.
- Ensure a task's container cannot accidentally mount another task's worktree.
- Verify that changes made inside `/workspace` are visible in the corresponding host worktree.
- Avoid mounting host credentials, home directories, or unrelated sensitive paths.

**Acceptance checks:**
- Task A's container is mounted to Task A's worktree.
- Task B's container is mounted to Task B's worktree.
- A file changed in the container appears in the correct worktree.
- The change does not appear in the other task's working directory.

### Step 4: Implement Controlled Command and Test Execution

**Goal:** Run code mutations and execution commands inside the sandbox.

**Tasks:**
- Provide a controlled execution interface for commands inside the task container.
- Route patch application, linters, build commands, and tests to Docker.
- Capture the process exit code, standard output, and standard error.
- Apply execution timeouts and handle cancellation where needed.
- Validate workspace paths and avoid unsafe host-side shell execution.
- Reuse the same container for the Coder and Tester phases of a task.

**Acceptance checks:**
- A command runs inside the intended task container.
- Exit code, stdout, and stderr are returned to the caller.
- Timeouts and command failures are handled predictably.
- Coder changes can be tested in the same container without rebuilding it.

### Step 5: Implement Diff Collection and Cleanup

**Goal:** Capture task changes and release resources reliably.

**Tasks:**
- Collect the task's changes with native Git diff operations on the corresponding worktree.
- Associate the diff with the correct task ID.
- Stop and remove the task container after its required phases finish.
- Remove temporary worktrees when appropriate and safe.
- Ensure cleanup also runs after failures or cancellation.
- Preserve the diff and test logs as task artifacts before deleting temporary resources.

**Acceptance checks:**
- The collected diff corresponds to the correct task.
- Test logs and execution outcomes remain available after cleanup.
- Containers are not left running after task completion.
- Worktrees are not deleted while still needed by an active task.

### Step 6: Test Concurrent Task Isolation

**Goal:** Verify that multiple tasks can operate on the same repository without sharing mutable workspaces.

**Tasks:**
- Launch at least two tasks against the same repository.
- Give each task a distinct worktree, branch, and sandbox.
- Modify files in both tasks concurrently.
- Confirm that each task sees its own working-tree changes.
- Verify that each task's commands run in its own container.
- Document how merge conflicts are surfaced for later review or pull-request handling.

**Acceptance checks:**
- The tasks use different worktree paths and branches.
- Each container mounts only its assigned worktree.
- Changes made by one task do not overwrite the other task's working files.
- Diffs and logs are attributed to the correct task.
- Conflicting changes are handled through normal Git conflict resolution rather than silently overwritten.

## Suggested Component Breakdown

| Component | Responsibility |
|---|---|
| `WorktreeManager` | Create, track, inspect, and remove task worktrees and branches. |
| `SandboxManager` | Create and manage task-specific Docker containers and security settings. |
| `WorkspaceMount` | Configure and validate the worktree bind mount at `/workspace`. |
| `CommandRunner` | Execute commands inside the correct container and capture results. |
| `DiffCollector` | Retrieve and store the task's Git diff. |
| `TaskLifecycleCoordinator` | Orchestrate setup, execution, testing, artifact collection, and cleanup. |

These names are proposed component names, not names specified by the architecture document. They can be adapted to the existing repository conventions.

## End-to-End Definition of Done

Section 2 is ready when:

- [ ] Each task receives its own Git worktree and branch.
- [ ] Each task receives a restricted Docker container.
- [ ] The container mounts only its assigned task workspace.
- [ ] Code mutations and test commands run inside Docker.
- [ ] The Coder and Tester reuse the same container for a task.
- [ ] The task's diff, exit codes, and logs are collected.
- [ ] Containers and temporary worktrees are cleaned up safely.
- [ ] Concurrent-task isolation tests pass.
- [ ] Failure and cancellation paths do not leave unmanaged resources.

## Scope Notes

This plan covers the recommended implementation order for Section 2: Git worktree isolation, Docker sandboxing, workspace mounting, controlled execution, diff collection, lifecycle cleanup, and concurrency validation.

The broader AST/SQLite indexing engine and its copy-on-write synchronization are described elsewhere in the architecture document and are not implemented by this Section 2 plan itself.

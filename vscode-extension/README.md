# GAINT Interns Hub VS Code Extension

Version 4.1 connects automatically from the downloaded project. It validates
required project files, runs local checks and submits the current checkpoint
plus a limited snapshot of the required text-source modules. The complete
project, local database, secrets and dependency folders remain on the
student's computer.

## Student installation

1. Extract the downloaded project ZIP.
2. Double-click `OPEN_IN_VSCODE.bat`.
3. The script installs and verifies the included GAINT VSIX automatically.
4. It opens the complete project folder in VS Code.
5. Run **GAINT: Open Current Task** if the checkpoint is not already open.
6. Work in the real project and the required checkpoint file.
7. Run **GAINT: Submit Current Task**.
8. If the project checks and Judge0 checks pass, the next task unlocks.
9. After the final task, the extension creates a clean runnable ZIP beside the
   project folder and the portal enables the certificate automatically.

If VS Code storage is cleared, run **GAINT: Repair Project Connection**. The
same starter reconnects without copying a token.

There is no token copy, Task ID, Git requirement, browser code form, full
project upload, Mentor approval or viva.

Students do not use the Marketplace, copy extension source, or run a separate
extension installer.

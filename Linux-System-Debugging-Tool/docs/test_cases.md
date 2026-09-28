# Test Cases

| ID | Program | Expected observation |
|---|---|---|
| TC01 | normal_test | Normal exit, status 0 |
| TC02 | file_error | Failed file open, ENOENT |
| TC03 | invalid_fd | Failed read, EBADF |
| TC04 | permission_error | Permission-related behavior depending on execution privileges |
| TC05 | abnormal_exit | Termination by SIGTERM |
| TC06 | segmentation_fault | Termination by SIGSEGV |

For each test, capture terminal output, generated trace, and report as evidence.

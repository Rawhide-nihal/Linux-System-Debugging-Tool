#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define LDST_INPUT_SIZE 64
#define REPORT "results/autodebug_report.txt"
#define TRACE "logs/autodebug_trace.txt"
#define NUM_TESTS 7

static void clear_screen(void)
{
    printf("\033[2J\033[H");
}

static void pause_screen(void)
{
    printf("\nPress ENTER to return to the main menu...");
    fflush(stdout);
    int c;
    while ((c = getchar()) != '\n' && c != EOF) {}
}

static int ask_number(const char *prompt, int min, int max)
{
    char b[LDST_INPUT_SIZE];
    long v;
    char *e;
    for (;;) {
        printf("%s", prompt);
        fflush(stdout);
        if (!fgets(b, sizeof(b), stdin)) return -1;
        v = strtol(b, &e, 10);
        while (isspace((unsigned char)*e)) e++;
        if (e != b && *e == '\0' && v >= min && v <= max) return (int)v;
        printf("Invalid choice. Enter %d-%d.\n", min, max);
    }
}

static int run_command(char *const argv[])
{
    fflush(stdout);
    fflush(stderr);
    pid_t p = fork();
    if (p < 0) {
        perror("fork");
        return -1;
    }
    if (p == 0) {
        execvp(argv[0], argv);
        perror("execvp");
        _exit(127);
    }
    int st;
    if (waitpid(p, &st, 0) < 0) {
        perror("waitpid");
        return -1;
    }
    if (WIFEXITED(st)) return WEXITSTATUS(st);
    if (WIFSIGNALED(st)) return 128 + WTERMSIG(st);
    return 1;
}

static int executable_exists(const char *p)
{
    return access(p, X_OK) == 0;
}

static void header(void)
{
    printf("╔══════════════════════════════════════════════════════════╗\n"
           "║          LINUX SYSTEM DEBUGGING TOOL (LDST)             ║\n"
           "║                    v2.0                                  ║\n"
           "╠══════════════════════════════════════════════════════════╣\n"
           "║  OS/System Programming Project • Interactive Console    ║\n"
           "╚══════════════════════════════════════════════════════════╝\n\n");
}

static const char *test_path(int n)
{
    switch (n) {
        case 1: return "tests/normal_test";
        case 2: return "tests/file_error";
        case 3: return "tests/invalid_fd";
        case 4: return "tests/abnormal_exit";
        case 5: return "tests/segmentation_fault";
        case 6: return "tests/permission_error";
        case 7: return "tests/system_call_error";
        default: return NULL;
    }
}

static const char *test_name(int n)
{
    switch (n) {
        case 1: return "Normal execution";
        case 2: return "File access failure (ENOENT)";
        case 3: return "Invalid file descriptor (EBADF)";
        case 4: return "Abnormal termination (SIGTERM)";
        case 5: return "Segmentation fault (SIGSEGV)";
        case 6: return "Permission failure (EACCES)";
        case 7: return "System call error (read invalid FD)";
        default: return "Unknown";
    }
}

static int choose_test(void)
{
    printf("\n┌──────────────── TEST PROGRAMS ────────────────┐\n");
    for (int i = 1; i <= NUM_TESTS; i++) {
        printf("│ %d. %-43s │\n", i, test_name(i));
    }
    printf("│ 0. Back                                        │\n"
           "└───────────────────────────────────────────────┘\n");
    return ask_number("Select a test: ", 0, NUM_TESTS);
}

static void ensure_build(void)
{
    if (!executable_exists("./debugger") || !executable_exists("./autodebug")) {
        printf("\n[System] Required executables are missing. Building project...\n");
        char *a[] = {"make", NULL};
        int rc = run_command(a);
        if (rc != 0) printf("Build returned status %d.\n", rc);
    }
    char *b[] = {"make", "tests", NULL};
    run_command(b);
}

static void run_debugger_menu(void)
{
    int t = choose_test();
    if (t <= 0) return;
    ensure_build();
    const char *p = test_path(t);
    char *a[] = {"./debugger", (char *)p, NULL};
    printf("\nLaunching debugger for %s...\n\n", p);
    run_command(a);
    pause_screen();
}

static void run_autodebug_menu(void)
{
    int t = choose_test();
    if (t <= 0) return;
    ensure_build();
    const char *p = test_path(t);
    char *a[] = {"./autodebug", (char *)p, NULL};
    printf("\nLaunching AutoDebugger for %s...\n\n", p);
    run_command(a);
    pause_screen();
}

static void run_test_menu(void)
{
    int t = choose_test();
    if (t <= 0) return;
    ensure_build();
    const char *p = test_path(t);
    char *a[] = {(char *)p, NULL};
    printf("\nRunning test program directly: %s\n\n", p);
    run_command(a);
    pause_screen();
}

static void view_file_content(const char *path, const char *title)
{
    clear_screen();
    header();
    printf("--- %s ---\n\n", title);
    FILE *f = fopen(path, "r");
    if (!f) {
        printf("No report has been generated yet.\nFile: %s\n", path);
        pause_screen();
        return;
    }
    char b[1024];
    while (fgets(b, sizeof(b), f)) fputs(b, stdout);
    fclose(f);
    pause_screen();
}

static void process_info(void)
{
    clear_screen();
    header();
    printf("--- CURRENT PROCESS INFORMATION ---\n\n");
    char *a[] = {"ps", "-o", "pid,ppid,state,%cpu,%mem,comm,args", "--forest", NULL};
    run_command(a);
    printf("\nThe debugger records the target PID and /proc snapshot during a debugger run.\n");
    pause_screen();
}

static void complete_demo(void)
{
    clear_screen();
    header();
    ensure_build();
    for (int t = 1; t <= NUM_TESTS; t++) {
        const char *p = test_path(t);
        printf("\n============================================================\n"
               "TEST %d/%d: %s\n"
               "============================================================\n",
               t, NUM_TESTS, test_name(t));
        char *a[] = {"./autodebug", (char *)p, NULL};
        run_command(a);
    }
    pause_screen();
}

static void menu(void)
{
    clear_screen();
    header();
    printf("╔══════════════════════════════════════════════════════════╗\n"
           "║                                                          ║\n"
           "║   1. Run Debugger                                        ║\n"
           "║   2. Run AutoDebugger                                    ║\n"
           "║   3. Run Test Program                                    ║\n"
           "║   4. View Latest Diagnosis                               ║\n"
           "║   5. View System Call Trace                              ║\n"
           "║   6. View Process Information                            ║\n"
           "║   7. Run Complete Demonstration                          ║\n"
           "║   8. Exit                                                ║\n"
           "║                                                          ║\n"
           "╚══════════════════════════════════════════════════════════╝\n\n");
}

int main(void)
{
    for (;;) {
        menu();
        int c = ask_number("Select an option: ", 1, 8);
        if (c < 0) return 0;
        switch (c) {
            case 1: run_debugger_menu(); break;
            case 2: run_autodebug_menu(); break;
            case 3: run_test_menu(); break;
            case 4: view_file_content(REPORT, "LATEST AUTO DIAGNOSIS"); break;
            case 5: view_file_content(TRACE, "LATEST SYSTEM CALL TRACE"); break;
            case 6: process_info(); break;
            case 7: complete_demo(); break;
            case 8:
                clear_screen();
                printf("Linux System Debugging Tool closed.\n");
                return 0;
        }
    }
}

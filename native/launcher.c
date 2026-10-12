#define _POSIX_C_SOURCE 200809L
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Small native entry point; Python and WebKit stay separate system dependencies. */
int main(int argc, char **argv) {
    char prefix[PATH_MAX], script[PATH_MAX], python[PATH_MAX];
    ssize_t length = readlink("/proc/self/exe", prefix, sizeof(prefix) - 1);
    if (length < 0 || length >= (ssize_t)sizeof(prefix) - 1) {
        fputs("mdview: cannot locate the installed executable\n", stderr);
        return 1;
    }
    prefix[length] = '\0';
    for (int level = 0; level < 2; level++) {
        char *slash = strrchr(prefix, '/');
        if (!slash) return 1;
        *slash = '\0';
    }
    int script_length = snprintf(script, sizeof(script), "%s/share/mdviewer/mdview.py", prefix);
    int python_length = snprintf(python, sizeof(python), "%s/share/mdviewer/venv/bin/python", prefix);
    if (script_length < 0 || script_length >= (int)sizeof(script) ||
        python_length < 0 || python_length >= (int)sizeof(python)) {
        fputs("mdview: installation path is too long\n", stderr);
        return 1;
    }
    if (access(script, R_OK) != 0) {
        fputs("mdview: application files are missing; rerun the installer\n", stderr);
        return 1;
    }
    char **arguments = calloc((size_t)argc + 2, sizeof(char *));
    if (!arguments) {
        perror("mdview");
        return 1;
    }
    arguments[0] = access(python, X_OK) == 0 ? python : "python3";
    arguments[1] = script;
    for (int index = 1; index < argc; index++) arguments[index + 1] = argv[index];
    execvp(arguments[0], arguments);
    perror("mdview: cannot start Python");
    free(arguments);
    return 1;
}

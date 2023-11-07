 // This header file was generated on
// z5214348.web.cse.unsw.edu.au/header_generator/

// header guard: https://en.wikipedia.org/wiki/Include_guard
// This avoids errors if this file is included multiple times
// in a complex source file setup

#ifndef WRAP_H
#define WRAP_H

// #includes

#include <stdio.h>
#include <stdlib.h>
#include "wrap.c"

// Functions

int __wrap_execl(const char *path, const char *arg, ...);
int __wrap_execle(const char *path, const char *arg, .../*, char *const envp[]*/);
int __wrap_execlp(const char *file, const char *arg, ...);
int __wrap_execv(const char *path, char *const argv[]);
int __wrap_execve(const char *path, char *const argv[], char *const envp[]);
int __wrap_execvp(const char *file, char *const argv[]);
int __wrap_system(const char* Command);

extern FILE *__wrap_popen(const char *command, const char *mode);

// End of header file
#endif

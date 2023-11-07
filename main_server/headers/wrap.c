#include <stdlib.h>
#include <stdio.h>

int __wrap_system(const char* Command)
{
    fprintf(stderr,"Function system is not allowed.\n");
    exit(-1);
}

int __wrap_execl(const char *path, const char *arg, ...)
{
    fprintf(stderr,"Function execl is not allowed.\n");
    exit(-1);
}

int __wrap_execlp(const char *file, const char *arg, ...)
{
    fprintf(stderr,"Function execlp is not allowed.\n");
    exit(-1);
}

int __wrap_execle(const char *path, const char *arg, .../*, char *const envp[]*/)
{
    fprintf(stderr,"Function execle is not allowed.\n");
    exit(-1);
}

int __wrap_execv(const char *path, char *const argv[])
{
    fprintf(stderr,"Function execv is not allowed.\n");
    exit(-1);
}

int __wrap_execvp(const char *file, char *const argv[])
{
    fprintf(stderr,"Function execvp is not allowed.\n");
    exit(-1);
}

int __wrap_execve(const char *path, char *const argv[], char *const envp[])
{
    fprintf(stderr,"Function execve is not allowed.\n");
    exit(-1);
}

extern FILE *__wrap_popen(const char *command, const char *mode)
{
    fprintf(stderr,"Function popen is not allowed.\n");
    exit(-1);
}

// FILE *__cdecl __wrap_fopen(const char *_FileName, const char *_Mode)
// {
//     fprintf(stderr,"Function fopen is not allowed.\n");
//     exit(-1);
// }

// errno_t __cdecl __wrap_fopen_s(FILE **_Stream, const char *_FileName, const char *_Mode)
// {
    
//     fprintf(stderr,"Function fopen_s is not allowed.\n");
//     exit(-1);
// }

// FILE *__cdecl __wrap__wfopen(const wchar_t *_FileName, const wchar_t *_Mode)
// {
    
//     fprintf(stderr,"Function _wfopen is not allowed.\n");
//     exit(-1);
// }
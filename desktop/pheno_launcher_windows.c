/* Launch the adjacent Strawberry runtime without cmd.exe or PATH lookup. */
#include <windows.h>
#include <process.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <wchar.h>

static wchar_t *quote(const wchar_t *value) {
    wchar_t *result = calloc(2 * wcslen(value) + 3, sizeof(wchar_t));
    if (!result) return NULL;
    wchar_t *out = result;
    *out++ = L'"';
    size_t slashes = 0;
    for (;; value++) {
        if (*value == L'\\') { slashes++; continue; }
        size_t count = (*value == L'"' || !*value) ? slashes * 2 : slashes;
        while (count--) *out++ = L'\\';
        slashes = 0;
        if (!*value) break;
        if (*value == L'"') *out++ = L'\\';
        *out++ = *value;
    }
    *out++ = L'"';
    *out = 0;
    return result;
}

int wmain(int argc, wchar_t **argv) {
    wchar_t root[32768], perl[32768], script[32768], cache[32768];
    DWORD length = GetModuleFileNameW(NULL, root, 32768);
    if (!length || length >= 32768) return 1;
    wchar_t *end = wcsrchr(root, L'\\');
    if (!end) return 1;
    *end = 0;
    end = wcsrchr(root, L'\\');
    if (!end) return 1;
    *end = 0;
    if (wcslen(root) + 40 >= 32768) return 1;
    swprintf(perl, 32768, L"%ls\\perl\\bin\\perl.exe", root);
    swprintf(script, 32768, L"%ls\\perl\\bin\\pheno-ranker", root);
    swprintf(cache, 32768, L"%ls\\inline", root);
    _wputenv_s(L"PERL5LIB", L"");
    _wputenv_s(L"PERLLIB", L"");
    _wputenv_s(L"PERL5OPT", L"");
    _wputenv_s(L"PHENO_RANKER_INLINE_DIR", cache);
    const wchar_t **args = calloc((size_t)argc + 2, sizeof(wchar_t *));
    if (!args) return 1;
    args[0] = quote(perl);
    args[1] = quote(script);
    for (int i = 1; i < argc; i++) args[i + 1] = quote(argv[i]);
    for (int i = 0; i <= argc; i++) if (!args[i]) return 1;
    intptr_t status = _wspawnv(_P_WAIT, perl, args);
    for (int i = 0; i <= argc; i++) free((void *)args[i]);
    free(args);
    if (status == -1) { perror("Cannot start bundled Perl"); return 1; }
    return (int)status;
}

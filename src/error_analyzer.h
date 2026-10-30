#ifndef ERROR_ANALYZER_H
#define ERROR_ANALYZER_H

const char *error_description(int code);
const char *error_name_from_code(int code);
int error_code_from_name(const char *name);
const char *signal_description(int signal_number);
const char *signal_short_name(int signal_number);

#endif

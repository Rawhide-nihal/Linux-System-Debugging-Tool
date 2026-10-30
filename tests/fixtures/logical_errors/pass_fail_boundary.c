#include <stdio.h>

/*
 * Specification: A student PASSES if marks >= 35.
 * Bug: The condition incorrectly tests marks > 35.
 */
int is_passing(int marks) {
    return marks > 35;
}

int main(void) {
    int marks = 0;
    if (scanf("%d", &marks) != 1) {
        return 1;
    }
    if (is_passing(marks)) {
        printf("PASS\n");
    } else {
        printf("FAIL\n");
    }
    return 0;
}

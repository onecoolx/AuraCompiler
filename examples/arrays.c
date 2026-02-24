/* Array operations */

int main() {
    int arr[10];
    int i;
    
    /* Initialize array */
    for (i = 0; i < 10; i = i + 1) {
        arr[i] = i * 2;
    }
    
    /* Sum array */
    int sum = 0;
    for (i = 0; i < 10; i = i + 1) {
        sum = sum + arr[i];
    }
    
    return sum;
}

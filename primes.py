import random

def is_prime(n, k=5):
    """
    Miller-Rabin primality test.
    
    Args:
        n: The number to test for primality.
        k: The number of rounds of testing to perform (higher = more accurate).
           
    Returns:
        True if n is probably prime, False if n is definitely composite.
    """
    # Handle some simple cases first
    if n <= 1:
        return False
    elif n <= 3:
        return True
    elif n % 2 == 0:
        return False
    
    # Write n-1 as d*2^sis
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    
    # Test for k rounds
    for _ in range(k):
        a = random.randint(2, n - 2)
        x = pow(a, d, n)
        
        if x == 1 or x == n - 1:
            continue
            
        for __ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
            
    return True

# Example usage
def test1():
    test_numbers = [2, 3, 5, 7, 11, 13, 15, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
    for num in test_numbers:
        print(f"{num}: {'Prime' if is_prime(num) else 'Composite'}")
    
    # Test some larger numbers
    large_numbers = [1009, 1013, 10007, 104729]  # Some known primes
    for num in large_numbers:
        print(f"{num}: {'Prime' if is_prime(num) else 'Composite'}")


def test2():
    for i in range(1000):
        if is_prime(i):
            print(i)

if __name__ == "__main__":
    test2()
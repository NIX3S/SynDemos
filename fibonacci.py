def generate_fibonacci_sequence(n):
    sequence = [0, 1]
    while len(sequence) < n:
        next_value = sequence[-1] + sequence[-2]
        sequence.append(next_value)
    return sequence

def plot_fibonacci_sequence(sequence):
    import matplotlib.pyplot as plt
    plt.plot(range(len(sequence)), sequence)
    plt.title('Sequence de Fibonacci')
    plt.xlabel('Index')
    plt.ylabel('Valeur de la suite')
    plt.show()
x = generate_fibonacci_sequence(10)
plot_fibonacci_sequence(x)
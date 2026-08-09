"""Nothing here has a provable type, so nothing may be reported."""

result = load_result()
counts = result.get_counts()
dists = result.quasi_dists

sampler = build_sampler()
sampler.run([build_circuit()])

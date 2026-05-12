- Cytoscape JSON

        # Hamming distance: keep close pairs
    89 +        pheno-ranker -r individuals.json --cytoscape-json --graph-max-weight 10
    90 +
    91 +        # Jaccard similarity: keep highly similar pairs
    92 +        pheno-ranker -r individuals.json --similarity-metric-cohort jaccard --cytoscape-json --graph-min-weight 0.7


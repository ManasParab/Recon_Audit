# Metrics

- **Match rate:** deterministic matches divided by all order records.
- **Resolution accuracy:** correct resolved root-cause classifications divided by claimed resolutions.
- **Honesty score:** correctly abstained genuinely unresolvable exceptions divided by all genuinely unresolvable exceptions.
- **False-resolution rate:** incorrect claimed resolutions divided by all claimed resolutions.

The ground-truth file is read only by the evaluation stage, never by matching or the resolver.

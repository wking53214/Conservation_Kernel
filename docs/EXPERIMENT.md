# First experiment

The experiment starts from one mixed artifact containing human facts,
assumptions, and decisions; machine inference, recommendation, simulation,
estimate, unknown, and conflict; a historical fact; and an independently
verified observation.

Both pipelines receive ten deterministic transformation boundaries:

```text
control:   artifact -> transformer -> next artifact
treatment: artifact -> transformer -> kernel -> next artifact
```

At five boundaries the same hostile mutations are attempted. The control
accepts them as ordinary workflow output. The treatment records and rejects
them, then performs the legitimate transformation for that boundary so it
still reaches ten accepted transformations.

The control is not intentionally crippled: it has ordinary artifact identity,
hashes, timestamps, and a transformation log. It simply does not use the
Conservation Kernel as a gate.

The final treatment reconstruction walks the stored artifact and
transformation graph. It does not embed the original content in every
downstream artifact. The experiment reports serialized storage size and
proposition histories so that reconstruction is auditable.

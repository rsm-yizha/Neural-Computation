# Verification of the verifier

Seven tests passed using test_verify.py: one unmodified control and six intentionally corrupted temporary copies.
- A digital EEG sample changed by one integer step: rejected.
- Event onset shifted by one sample (0.00625 seconds): rejected.
- Event duration increased by one sample: rejected.
- Execution labeled as imagery: rejected.
- Incorrect original T code: rejected.
- First two channels.tsv rows exchanged: rejected by the default MNE-BIDS channel-mismatch error.

The production BIDS output was not modified by these tests.
The final script completed from scratch in the fresh bids-repeat directory, including round-trip checks and validator.
All 25 BIDS files are byte-identical between bids/ and bids-repeat/.

Run tests: python -B test_verify.py
The initial development output is retained separately in bids-initial-inspection; it is not the verified deliverable.

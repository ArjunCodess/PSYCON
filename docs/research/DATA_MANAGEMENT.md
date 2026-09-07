# Research data management

Participant data must stay in the approved encrypted study store, outside this Git repository. The project repository may contain schemas, code, synthetic fixtures, aggregate reports approved for release, and manifests that cannot identify a person.

## Data layout and lineage

Each immutable dataset version uses this structure in the protected store:

```text
dataset-1.0.0/
  raw/
  features/
  metadata/
  logs/
  manifests/
  withdrawals/
  backup-verification/
```

Raw objects keep their device timestamps, sequence numbers, checksums, session IDs, firmware versions, and content hashes. Feature records keep source-object hashes, window bounds, extractor version, configuration, quality state, and label version. A dataset manifest lists every included file, hash, consent state, exclusion decision, and parent dataset version. Corrections create a new version; they never rewrite an old manifest.

Model outputs live under an immutable model version with the source dataset version, code revision, dependency versions, split assignment hash, random seed, fitted preprocessing, candidate results, predictions, errors, charts, report, and release decision.

## Access and protection

Use role-based access with named accounts, multi-factor authentication where available, encrypted transport, encrypted storage, and an audit log. The access register records each person, role, approved purpose, granted date, review date, and revoked date. Review access on the schedule approved for the study and remove it when the purpose ends.

Keep the participant identity key in a separate restricted system. Do not copy it into session metadata, logs, filenames, model artifacts, exports, issue trackers, or this repository. Do not log raw audio, transcripts, embeddings, tokens, secrets, or free-text participant statements.

Raw audio, transcripts, voice embeddings, derived features, exports, and backups follow the distinct retention periods stated in the approved consent form. An expired item becomes unavailable for new processing and enters the verified deletion workflow.

## Backup verification

Create encrypted backups in an approved separate location. After each dataset freeze, compare the backup file list, byte counts, and SHA-256 hashes with the signed source manifest. Record the backup identifier, storage class, operator, verification time, manifest hash, missing or mismatched objects, and result. A Git commit is version history, not a participant-data backup.

Test restoration into an isolated approved location on the review schedule. A backup does not count as verified until the restore produces the expected file hashes and the operator records cleanup of the restored copy.

## Withdrawal and deletion

1. Authenticate the request using the approved identity-key process without adding identity data to the research store.
2. Resolve the participant ID and immediately mark it withdrawn so ingestion, feature extraction, training, and export reject affected sessions.
3. Record affected raw, feature, transcript, embedding, export, and model versions by manifest hash.
4. Delete active copies under the approved policy and record object identifiers, hashes, operator, time, and result in the restricted withdrawal log.
5. Expire backup copies under the approved retention policy and verify that the next restore test cannot recover them after expiry.
6. Review models trained on the withdrawn records. Create a new dataset version and retrain when required; preserve the audit record without preserving withdrawn content.
7. Confirm completion through the approved participant contact process and document any approved limit for aggregate results already published.

## Release review

Before releasing an aggregate report, confirm that consent permits the use, small cells cannot expose a participant, free text and audio are absent, participant IDs are removed or replaced for the release, metadata does not permit linkage, and the report identifies dataset and model versions. The reviewer records approval against the exact export hash.


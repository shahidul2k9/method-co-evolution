# Method History Batch Exporter

This is a small IntelliJ Platform plugin starter for batch-exporting method history
from a directory of oracle JSON files.

## What It Does

- adds `Tools -> Export Method History Batch`
- prompts for:
  - repository root
  - oracle JSON directory
  - output directory
- reads each oracle JSON file
- uses IntelliJ VCS file history APIs to load file revisions
- uses Java PSI to locate the target method in each revision
- writes one JSON history file per oracle JSON

## Expected Oracle JSON Shape

Each JSON file should include:

- `repositoryName`
- `file`
- `element`
- `startLine`
- `endLine`

## Notes

- this plugin does not automate IntelliJ's `Show History for Method` UI directly
- instead, it uses IntelliJ PSI + VCS APIs inside the IDE to reconstruct method history in batch

## Build

Open this folder as a Gradle project in IntelliJ IDEA and run the `runIde` task.

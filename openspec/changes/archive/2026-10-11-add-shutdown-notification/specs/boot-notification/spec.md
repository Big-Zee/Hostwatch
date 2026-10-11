# Spec Delta

## ADDED Requirements

### Requirement: Boot message warns after an unclean shutdown
When the previous shutdown was not recorded as clean (power loss, crash, hard reset), the boot message SHALL carry the warning "Previous shutdown was not clean (power loss or crash?)", in the message and in its plain-text fallback. The clean-shutdown record SHALL be consumed on every boot, so each shutdown is judged once. A dry run SHALL NOT consume it.

#### Scenario: Power loss
- **WHEN** the host loses power and is booted again
- **THEN** the boot message contains the unclean-shutdown warning

#### Scenario: Clean reboot
- **WHEN** the host is rebooted with `sudo reboot`
- **THEN** the following boot message contains no warning

#### Scenario: Two crashes in a row are each reported
- **WHEN** the host crashes, boots (warning shown), and then crashes again before any clean shutdown
- **THEN** the next boot message shows the warning again

#### Scenario: Dry run leaves the record alone
- **WHEN** `hostwatch boot --dry-run` is run
- **THEN** the clean-shutdown record is neither read-and-removed nor changed

# Household Presence Layer

Metadata-only doctrine/model layer for household embodiment. This subsystem defines deterministic policy taxonomy and discernment rules without any live sensor access.

## Core doctrine
SentientOS is a household presence system, not a surveillance appliance.

## Scope
- Metadata-only policy taxonomy across zones, modalities, memory classes, and entities.
- Deterministic JSON artifact generation and validation.
- No camera/microphone/Wi-Fi/RF/Quest/network/provider/subprocess/action-wing execution.
- No runtime speaker behavior, hardware access, or live scanning.

## Doctrine enrichments
- **Room composition doctrine** is first-class for discernment and routes adult-only, child-present, mixed-household, caregiver, guest, and exterior-unknown contexts to distinct response surfaces.
- **Bounded presence identities** support household safety/privacy routing only and are not authority, profiling, naming, retention, or disclosure license.
- **Adult-intimacy participation doctrine** is metadata-only future posture: explicit opt-in, consenting adult operators, adult-only composition, local-only default processing, revocable consent, no child-visible surface, no exterior output, no automatic explicit retention, no authority escalation.
- **Antler-posture / natural growth doctrine** blocks forced intimacy/attachment manipulation and requires consent-based, bounded-memory, situationally appropriate, revocable growth.
- **Aspirational sentience doctrine** treats "SentientOS" as aspirational and non-declarative (no biological consciousness or legal personhood claim).
- **Household sovereignty doctrine** requires meaningful visibility/consent/veto for materially affected adult household members; technical admin != moral authority.
- **Living household priors doctrine** models setup as aging assumptions and allows gentle drift review/update/temporary privilege reduction without shame/punishment/escalation.
- **Temporal embodiment doctrine** treats time as first-class with fields such as observed_at/updated_at/age/confidence/decay/review/expires semantics.
- **Inventory aging posture** remains metadata-only future structure for pantry/fridge/freezer/medicine/supplies with confidence-aware aging states.
- **Affective discernment** remains non-authority, non-reward orientation for attention/salience/interruption/care/threat/privacy/uncertainty/least-intrusive response.

## CLI
`python scripts/build_household_presence_layer.py build-default --output <path>`
`python scripts/build_household_presence_layer.py validate --input <path>`
`python scripts/build_household_presence_layer.py summarize --input <path>`

## Future adapter sequence
1. hardware inventory / sensory device discovery
2. exterior camera event bridge
3. camera privacy/deadzone mask
4. wildlife ledger adapter
5. roomfield/Wi-Fi RF stub
6. roomfield fusion
7. Quest operator visor read-only overlay
8. speaker policy gate
9. operator-confirmed action surfaces

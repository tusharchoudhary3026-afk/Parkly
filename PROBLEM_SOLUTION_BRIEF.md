# Problem and solution brief

## Problem and users

Drivers need a reliable way to reserve parking for a time window with a clear price. Operators need to manage slots and exceptions without requiring dedicated parking hardware. Primary users are drivers, attendants, managers, and auditors.

## Selected approach

The product combines time-window booking, explainable slot allocation, QR and attendant entry/exit, a hardware-agnostic event API, tariff billing, an availability estimate, and human-reviewed exception flags. It deliberately contains no physical sensors, cameras, ANPR, barriers, automatic fines, bans, or blacklisting.

## Evidence labels and limits

- **PROJECT FILE:** the supplied feature-scope plan identifies missing booking windows, billing, real-time input, and a need for database setup in the prior report.
- **RESEARCH EVIDENCE:** the supplied plan cites external research concerning hardware limitations, privacy, booking enforcement, price fairness, and grace periods. Those sources are context only, not measured results of this implementation.
- **ASSUMPTION:** demo tariffs, time limits, and generated demand patterns are placeholders.
- **UNKNOWN:** real vendor event payloads, real demand, provider configuration, and legal obligations have not been verified.
- **SYNTHETIC / SIMULATED:** generated records and simulated payment/event surfaces must retain those labels.

## Alternatives considered

Sensor or camera detection would require hardware and introduces reliability and privacy concerns. Dynamic pricing is excluded from V1 because drivers need predictable pricing. Payment-only integration does not solve availability or reservations. Software events plus attendant fallback support the selected software-only scope.

## Human control

Drivers explicitly confirm bookings; tariff is previewed before confirmation. No-show release has no fine. Flags are review signals, not proof. Any penalty requires grace, notice, and reviewer action. Payment gateway is test mode only.

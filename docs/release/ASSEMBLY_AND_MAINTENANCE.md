# Assembly and maintenance guide

This guide does not replace the hardware schematic, component datasheets, or Week 6 validation runbook. Record the exact board, module, cell, charger, wire, connector, enclosure, firmware, and calibration revisions for every build.

## Assembly order

1. Inspect every board and cell for damage. Confirm component identity, polarity, pin labels, and the charger's protection arrangement against the purchased parts, not a generic listing.
2. Assemble and test the power path with a current-limited supply and no participant contact. Insulate every exposed conductor and restrain the cell without puncture, compression, or sharp bends.
3. Assemble the Wrist I2C bus using SDA `GPIO21` and SCL `GPIO22`. Confirm MAX30102 `0x57`, MPU6050 `0x68`, MCP9808 `0x18`, and ADS1115 `0x48` one at a time before running them together.
4. Connect the GSR front end to ADS1115 A0. Bench-test open circuit and known resistors, then measure excitation and fault current. Do not attach electrodes to a person until electrical review passes.
5. Assemble the Audio Module with INMP441 WS `GPIO25`, SCK `GPIO26`, SD `GPIO33`, and L/R to ground. Keep the microphone port open and mechanically isolated. Connect the TEMT6000 only to the documented analog input for the frozen hardware revision.
6. Load the identified firmware builds, run the individual-sensor stage, then pass the remaining Week 6 stages in order. A successful I2C scan alone does not establish calibration or continuous acquisition.
7. Fit the enclosure. Confirm rounded wearer-facing edges, optical contact, electrode separation, ventilation, reset and charge access, strain relief, strap integrity, battery restraint, insulation, and an unobstructed microphone port.
8. Complete the assembly checklist, photographs, electrical record, calibration records, one-hour physical stress test, and six-hour battery test. Apply the hardware revision label only after the record is complete.

## Before every use

- Check the hardware label and firmware versions against the approved build record.
- Inspect the cell, insulation, strap, electrodes, sensor window, microphone opening, enclosure, wiring, and connectors.
- Confirm charge state off-body, then disconnect charging and wired power before fitting the device.
- Run sensor initialization and address checks, verify time synchronization, and create a fresh anonymous session.
- Clean contact surfaces using a method compatible with the actual materials and allow them to dry.

## Weekly work

- Review reset, brownout, sensor, packet-loss, buffer, synchronization, and temperature logs.
- Inspect solder joints, connectors, cable strain relief, enclosure fasteners, strap, battery restraint, and charge port.
- Verify charging off-body and compare charge time and temperature with the accepted record.
- Build both firmware projects and record any dependency or toolchain change.

## Monthly work

- Repeat calibration checks and compare drift with the previous record.
- Review battery capacity, swelling, heat, damage, runtime, and protection behavior. Retire questionable cells.
- Inspect optical alignment, microphone isolation, electrode condition, enclosure fit, and all wearer-facing surfaces.
- Restore a backup into an isolated environment and verify manifest hashes.
- Review access, retention, withdrawals, deletion verification, model versions, open risks, and corrective actions.

## Change control

Increase the hardware revision after a wiring, PCB, power, charger, battery, sensor, connector, or enclosure change. Increase the firmware revision after acquisition, timing, buffering, communication, quality, power, or recovery behavior changes. Recalibrate affected sensors and rerun every downstream gate. Do not reuse an earlier runtime or safety pass for a changed build.

## Storage and transport

Power down both modules, disconnect electrodes, protect sensor and microphone openings, and transport cells in a nonconductive container that prevents crushing and short circuits. Store recordings and study exports only in the approved encrypted location. Store the identity key separately.

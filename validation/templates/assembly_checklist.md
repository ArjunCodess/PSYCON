# Assembly and safety checklist

- [ ] PCB, solder joints, polarity, component orientation, and connectors pass visual inspection.
- [ ] Protected cells are undamaged, restrained, insulated, and wired with correct polarity.
- [ ] The 3.3 V rail remains inside the approved range during boot, sensing, and wireless transmission.
- [ ] MAX30102, MPU6050, MCP9808, and ADS1115 appear at `0x57`, `0x68`, `0x18`, and `0x48` without intermittent loss.
- [ ] INMP441 records the expected channel without clipping, corruption, or DMA overrun.
- [ ] TEMT6000 responds to controlled dark and bright conditions.
- [ ] The enclosure has rounded edges, battery restraint, insulation, strain relief, accessible reset, and an unobstructed microphone port.
- [ ] Optical contact is flush, the strap is intact, and no conductor touches the wearer.
- [ ] GSR excitation and protection pass electrical review before electrode contact.
- [ ] No charger or wired external power is connected while worn or while GSR electrodes are attached.
- [ ] Low-battery warning, brownout handling, watchdog recovery, and controlled shutdown are demonstrated.
- [ ] Every failed item has an owner, corrective action, and retest record.


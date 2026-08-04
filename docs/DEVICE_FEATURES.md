# Device-Compatible Wrist Features

This is the frozen Week 2 software feature surface for the purchased Wrist Module. It operates on normalized device batches and does not require WESAD dataframe columns.

| Source | Raw normalized fields | Initial features |
| --- | --- | --- |
| MAX30102 | RED and IR ADC counts | Mean, standard deviation, minimum, maximum, range; validated pulse/HRV features follow after real sample-rate and signal-quality evidence |
| ADS1115/GSR | Raw ADC code | Mean, standard deviation, minimum, maximum, range; conductance units and tonic/phasic features remain blocked on the approved analog front end and calibration |
| MCP9808 | 0.01 °C converted to °C | Mean, standard deviation, minimum, maximum, range |
| MPU6050 accelerometer | mg converted to g | Vector-magnitude mean, standard deviation, minimum, maximum, range |
| MPU6050 gyroscope | 0.1 °/s converted to °/s | Vector-magnitude mean, standard deviation, minimum, maximum, range |
| Quality and power | Bit flags, sample indices, battery mV | Sample completeness, contact/saturation/disconnect fractions, battery voltage |

`ml/src/device_features.py` converts `protocol.wrist.WristBatch` records to a timestamped dataframe and deterministic feature dictionary. Raw ADC counts are intentionally retained until physical calibration supports physiological units. Missing samples reduce `sample_completeness`; quality flags remain model inputs and must also be used for abstention.

The next firmware implementation must supply the normalized fields or an equivalent binary/companion-status mapping. Exact MAX30102, ADS1115, and MPU6050 rates/ranges are hardware decisions recorded under “Questions for Saksham” in the build plan.

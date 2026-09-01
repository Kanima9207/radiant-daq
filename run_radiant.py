"""Run an 8-channel acquisition, filtering, triggering and buffering demo."""
import numpy as np
from radiant.acquisition import AcquisitionEngine
from radiant.buffer import SampleRingBuffer
from radiant.dsp import FIRPipeline, lowpass_taps
from radiant.trigger import ThresholdTrigger


def main():
    engine = AcquisitionEngine()
    pipeline = FIRPipeline(lowpass_taps(50_000))
    trigger = ThresholdTrigger(high=1.0, low=0.5, holdoff_samples=500)
    recorder = SampleRingBuffer(capacity_samples=7500)
    event_count = 0
    for chunk in range(4):
        indices = np.arange(chunk * 5000, (chunk + 1) * 5000)
        amplitudes = np.linspace(0.1, 0.8, 8)
        signals = np.sin(2 * np.pi * 1000 * indices[:, None] / 50_000) * amplitudes
        signals += 0.2 * np.sin(2 * np.pi * 10_000 * indices[:, None] / 50_000)
        # Three known CH0 pulse onsets exactly on chunk boundaries.
        for onset in (5000, 10_000, 15_000):
            signals[(indices >= onset) & (indices < onset + 1000), 0] += 3.0
        packet = engine.acquire(signals)
        filtered = pipeline.process(packet)
        events = trigger.process(filtered)
        recorder.append(filtered)
        event_count += len(events)
        print(f"sequence={packet.sequence} shape={packet.data.codes.shape} "
              f"first_sample={packet.first_sample} "
              f"start_ns={packet.timestamps_ns[0]} "
              f"clipped={np.count_nonzero(packet.data.clipped)} "
              f"events={len(events)} buffered={len(recorder)}")
        for event in events:
            print(f"  trigger: CH{event.channel_id} sample={event.sample_index} "
                  f"timestamp_ns={event.timestamp_ns} value={event.value_volts:.4f} V")
    snapshot = recorder.snapshot()
    print(f"ADC LSB: {engine.adc.lsb * 1000:.8f} mV")
    print(f"FIR group delay: {pipeline.group_delay_samples} samples (620 us at 50 kHz)")
    print(f"Total events: {event_count}; retained samples: {snapshot.first_sample}..19999; "
          f"overwritten: {recorder.overwritten_samples}")
    print("Simulation only; no host deadline or hardware timing claim.")


if __name__ == "__main__":
    main()

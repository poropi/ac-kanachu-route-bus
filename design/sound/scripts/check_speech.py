"""任意の背景音検査。Silero VAD の h/c 入力を持つ ONNX モデルを引数に渡す。"""
import argparse
from pathlib import Path

import numpy as np
import onnxruntime as ort
from scipy import signal
from scipy.io import wavfile

from build_samples import ENGINE, FX, SR, decode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    model = parser.parse_args().model
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), opts, providers=['CPUExecutionProvider'])
    clips = [(f'{source} {a:.3f}–{b:.3f}', decode(source, a, b))
             for source, a, b in ((23478, 2.10, 5.434), (23478, 27.60, 29.269),
                                  (22321, 23, 26.426), (58149, 92.46, 94.28),
                                  (58149, 100.78, 102.55), (96993, 0, 2.26), (96993, .04, .32))]
    for folder in (ENGINE, FX):
        for path in sorted(folder.glob('*.wav')):
            rate, pcm = wavfile.read(path)
            assert rate == SR
            clips.append((path.name, pcm.astype(float)/32768))
    for name, clip in clips:
        down = signal.resample_poly(clip, 1, 3).astype(np.float32)
        blocks = np.pad(down, (0, -len(down) % 512)).reshape(-1, 512)
        h = np.zeros((2, 1, 64), dtype=np.float32)
        c = np.zeros_like(h)
        scores = []
        for block in blocks:
            inputs = dict(input=block[None], h=h, c=c, sr=np.array(16000, dtype=np.int64))
            score, h, c = session.run(None, inputs)
            scores.append(score.item())
        print(f'{name:32s} max={max(scores):.3f}  p>=0.5: {sum(s>=.5 for s in scores)}/{len(scores)}')


if __name__ == '__main__':
    main()

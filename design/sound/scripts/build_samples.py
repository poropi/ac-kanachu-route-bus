"""神奈中バスの FMOD 用 WAV を原録音から作り、書き出した PCM を検査する。"""
from dataclasses import dataclass
from pathlib import Path
import subprocess

import numpy as np
from scipy import signal
from scipy.io import wavfile

OUT = Path(__file__).resolve().parents[1]
SRC = OUT.parents[1] / 'refs' / 'sound_src'
SR = 48000
LENGTH = SR * 3
RPMS = (600, 900, 1300, 1800, 2400)
REV_MIX = (.06, .18, .45, .72, .90)
ENGINE = OUT / 'engine'
CHECK = OUT / 'loopcheck'
FX = OUT / 'effects'


def decode(source, start, end):
    buf = subprocess.check_output([
        'ffmpeg', '-nostdin', '-v', 'error', '-i', str(SRC / f'{source}.mp3'),
        '-af', f'aresample={SR},atrim=start_sample={round(start*SR)}:end_sample={round(end*SR)}',
        '-ac', '1', '-f', 'f32le', '-'])
    return np.frombuffer(buf, '<f4').astype(float)


def rms(x):
    return np.sqrt(np.mean(np.square(x.astype(float))))


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-12))


def unit(x):
    return x / rms(x)


def overlap_head(x, length, overlap):
    # 先頭を「末尾のすぐ次の波形」から始め、内部で元の先頭へ戻す。
    weight = (1 - np.cos(np.linspace(0, np.pi, overlap))) / 2
    out = x[:length].copy()
    out[:overlap] = x[length:length+overlap]*(1-weight) + x[:overlap]*weight
    return out


def strongest_line(x, expected):
    # 予測位置の近傍でピークを実測する。局所雑音床との比も返す。
    nfft = 2 ** (len(x).bit_length() + 1)
    spec = abs(np.fft.rfft((x-x.mean())*np.hanning(len(x)), nfft))
    step = SR / nfft
    radius = max(1., expected*.025)
    left = round((expected-radius)/step)
    peak = left + np.argmax(spec[left:round((expected+radius)/step)+1])
    floor = np.r_[spec[round((expected-3*radius)/step):left],
                  spec[round((expected+radius)/step):round((expected+3*radius)/step)]]
    return peak*step, db(spec[peak]/np.median(floor))


@dataclass
class Bed:
    name: str
    source: int
    start: float
    end: float
    cycles: int
    audio: np.ndarray
    peaks: list

    @property
    def frequency(self):
        return self.cycles * SR / len(self.audio)

    def at(self, f):
        cycle_length = round(self.cycles * SR / f)
        period = signal.resample(self.audio, cycle_length)
        # 各録音の燃焼次数の位相を合わせ、混合時の低域の打ち消しを抑える。
        t = np.arange(len(period))
        phase = np.angle(np.sum(period*np.exp(-2j*np.pi*self.cycles*t/len(period))))
        period = np.roll(period, round(phase*SR/(2*np.pi*f)))
        overlap = round(5*SR/f)
        return unit(overlap_head(np.resize(period, LENGTH+overlap), LENGTH, overlap))


def bed(name, source, start, search_end, approx_hz, cycles):
    raw = decode(source, start, search_end)
    overlap = round(4 * SR / approx_hz)
    nominal = round(cycles * SR / approx_hz)
    # 低域の周期とアタックの位置が合う一周分を探す。
    pad = round(SR/approx_hz*.48)
    window = np.hanning(overlap)
    lo, hi = nominal-pad, nominal+pad
    test = raw[lo:hi+overlap]
    ref = raw[:overlap]
    corr = signal.correlate(test, ref*window, mode='valid', method='fft')
    energy = signal.correlate(test**2, window, mode='valid', method='fft')
    length = lo + np.argmax(corr / np.sqrt(np.maximum(1e-12, energy)))
    cut = raw[:length+overlap]
    peaks = [strongest_line(cut, approx_hz*h)[0] for h in (1, 2, 3)]
    return Bed(name, source, start, start+len(cut)/SR, cycles,
               overlap_head(cut, length, overlap), peaks)


def eq(x, hp, lp, shelf=0, cabin=False):
    # 周波数領域で循環 EQ を適用し、ゼロ詰めによるフィルター端の過渡を避ける。
    f = np.fft.rfftfreq(len(x), 1/SR)
    curve = (f**2/np.sqrt(f**4+hp**4)) / np.sqrt(1+(f/lp)**4)
    curve *= 10**((shelf*f**2/(f**2+720**2))/20)
    if cabin:
        curve *= 1 + .34*np.exp(-.5*(np.log2(np.maximum(f, 1)/122)/.48)**2)
    return np.fft.irfft(np.fft.rfft(x)*curve, n=len(x))


def make_engine(beds, index):
    rpm = RPMS[index]
    idle, rev, room = (b.at(rpm/30) for b in beds)
    # 実車内音から筐体振動の帯域だけを重ねる。
    room = unit(eq(room, 24, 145))
    result = {}
    for mode in ('load', 'coast'):
        load = mode == 'load'
        mix = REV_MIX[index] * (1 if load else .74)
        base = (1-mix)*idle + mix*rev
        for view in ('ext', 'int'):
            cabin = view == 'int'
            hp = 16 if load else 21
            lp = ((1420 if load else 880) if cabin else (6200 if load else 3050))
            shelf = (1.5 if load else -4.5) - (3 if cabin else 0)
            y = unit(eq(base, hp, lp, shelf, cabin))
            if cabin:
                y = unit(y + .22*room)
            level = (-19 if load else -22.5) + .5*index - int(cabin)
            result[view, mode] = (y*10**(level/20), mix, hp, lp, shelf)
    return result


def align_seams(result):
    # 同回転の4本を一緒に回して、アクセル混合や視点切替の位相関係を保つ。
    waves = np.array([v[0] for v in result.values()])
    candidates = np.arange(SR//4, SR)
    step = abs(waves[:, candidates]-waves[:, candidates-1])
    seam = candidates[np.argmin(np.max(step, axis=0))]
    return {k:(np.roll(v[0], -seam), *v[1:]) for k,v in result.items()}


def smooth_adjacent(sets):
    # 同じ燃焼次数で帯域の強さを比べ、隣り合う層を広帯域 EQ でなじませる。
    orders = 2**np.arange(-1.5, 7.51, .25)
    pitch_axis = np.log2(np.array(RPMS)/600)
    for key in sets[0]:
        envelopes = []
        for rpm, layers in zip(RPMS, sets):
            freq, power = signal.welch(layers[key][0], fs=SR, nperseg=32768)
            centers = orders*rpm/30
            env = [power[(freq>=c*2**(-.42)) & (freq<c*2**.42)].sum() for c in centers]
            envelopes.append(10*np.log10(np.maximum(env, 1e-15)))
        slope, _ = np.polyfit(pitch_axis, envelopes, 1)
        slope = np.clip(slope, -5, 5)
        for i, (rpm, layers) in enumerate(zip(RPMS, sets)):
            wave, *settings = layers[key]
            target = np.mean(envelopes, axis=0) + slope*(pitch_axis[i]-pitch_axis.mean())
            correction = np.clip(target-envelopes[i], -7, 7)
            freq = np.fft.rfftfreq(len(wave), 1/SR)
            relative = np.log2(np.maximum(freq, 1)/(rpm/30))
            gain = 10**(np.interp(relative, np.log2(orders), correction)/20)
            shaped = np.fft.irfft(np.fft.rfft(wave)*gain, n=len(wave))
            layers[key] = (unit(shaped)*rms(wave), *settings)


def save(path, x):
    assert np.max(abs(x)) < .999, f'波形の飽和 {path}'
    wavfile.write(path, SR, np.rint(x*32768).astype('<i2'))
    rate, data = wavfile.read(path)
    assert rate == SR and data.dtype == np.int16 and data.ndim == 1
    return data


def loop_stats(path, pcm):
    check = CHECK / f'loopcheck_{path.name}'
    wavfile.write(check, SR, np.tile(pcm, 3))
    rate, triple = wavfile.read(check)
    assert rate == SR and triple.dtype == np.int16
    assert np.array_equal(triple.reshape(3, -1), np.broadcast_to(pcm, (3,len(pcm))))
    data = triple.astype(int)
    width = round(.020*SR)
    results = []
    for cut in (len(pcm), 2*len(pcm)):
        left, right = data[cut-width:cut], data[cut:cut+width]
        jump = abs(right[0]-left[-1])
        local = np.abs(np.diff(np.r_[left, right]))
        assert jump <= np.percentile(local, 95)
        results.append((jump, max(local), db(rms(left)/32768), db(rms(right)/32768)))
    assert results[0] == results[1]
    return results[0]


def effect(name, source, start, end, noise, hp, lp, attack, release):
    raw = decode(source, start, end)
    background = decode(source, *noise)
    options = dict(fs=SR, nperseg=1024, noverlap=768)
    _, _, z = signal.stft(raw, **options)
    _, _, bg = signal.stft(background, **options)
    floor = np.median(abs(bg[:, 2:-2])**2, axis=1, keepdims=True)
    gain = np.sqrt(np.maximum(.05, 1-1.35*floor/(abs(z)**2+1e-16)))
    _, x = signal.istft(z*gain, **options)
    sos = signal.butter(2, [hp, lp], fs=SR, btype='bandpass', output='sos')
    x = signal.sosfilt(sos, x[:len(raw)])
    for tail, duration in ((False, attack), (True, release)):
        n = round(duration*SR)
        ramp = np.sin(np.linspace(0, np.pi/2, n))**2
        if tail:
            x[-n:] *= ramp[::-1]
        else:
            x[:n] *= ramp
    layer = ''
    if name.startswith('door_'):
        # 元の立ち上がりに混じる短い音を避け、別録りの排気で弁のアタックを作る。
        puff = decode(96993, .04, .32)
        puff = signal.sosfilt(signal.butter(2, [1300, 8200], fs=SR,
                                           btype='bandpass', output='sos'), puff)
        puff *= np.exp(-np.arange(len(puff))/(.066*SR))
        puff[:192] *= np.sin(np.linspace(0, np.pi/2, 192))**2
        puff[-960:] *= np.cos(np.linspace(0, np.pi/2, 960))**2
        x[:len(puff)] += unit(puff) * rms(x) * .8
        layer = ' ＋ 96993 0.040–0.320'
    x *= min(10**(-21/20)/rms(x), .83/np.max(abs(x)))
    p = FX / f'{name}.wav'
    pcm = save(p, x)
    return (f'| [{p.name}](effects/{p.name}) | {source} · {start:.3f}–{end:.3f}{layer} | '
            f'{len(pcm)/SR:.2f} | {hp}–{lp} | {noise[0]}–{noise[1]} | '
            f'{attack*1000:.0f} / {release*1000:.0f} | {db(rms(pcm)/32768):.2f} |')


def bands(x, ratio):
    # FMOD が両素材を幾何平均回転に移調した場合のオクターブ帯域 RMS。
    f, power = signal.welch(x.astype(float), fs=SR, nperseg=32768)
    return np.array([10*np.log10(power[(f*ratio>=lo)&(f*ratio<lo*2)].sum()+1e-20)
                     for lo in (40,80,160,320,640,1280)])


def main():
    for directory in (ENGINE, CHECK, FX):
        directory.mkdir(exist_ok=True)
    beds = [bed('アイドル',23478,2.1,6.0,30.0,96),
            bed('回転上昇後',23478,27.60,29.60,49.25,78),
            bed('車内振動',22321,23.0,27.0,27.48,90)]
    source_rows = []
    for b in beds:
        peaks = ' / '.join(f'{p:.2f}' for p in b.peaks)
        source_rows.append(f'| {b.name} | {b.source} | {b.start:.4f}–{b.end:.4f} | {peaks} | {b.frequency:.3f} |')
    rows,checks,comparisons = [],[],[]
    previous = {}
    rendered = [make_engine(beds,i) for i in range(len(RPMS))]
    smooth_adjacent(rendered)
    for rpm, layers in zip(RPMS, rendered):
        for (view,mode),(x,mix,hp,lp,shelf) in align_seams(layers).items():
            p = ENGINE / f'engine_{view}_{mode}_{rpm:04d}.wav'
            pcm = save(p, x)
            jump, maximum, pre, post = loop_stats(p, pcm)
            measurements = [strongest_line(pcm.astype(float), rpm/30*h) for h in (1,2,3)]
            valid = [peak/h for h,(peak,snr) in enumerate(measurements,1) if snr>=8]
            assert len(valid)>=2, (p, measurements)
            est = np.median(valid)*30
            assert abs(est/rpm-1)<.02
            room = view=='int'
            used = beds if room else beds[:2]
            sources = '；'.join(f'{b.source} {b.start:.4f}–{b.end:.4f}' for b in used)
            ratios = ' / '.join(f'{rpm/(30*b.frequency):.4f}' for b in used)
            peaks = ' / '.join(f'{f:.2f}' if snr>=8 else '—' for f,snr in measurements)
            rows.append(f'| [{p.stem}](engine/{p.name}) | {mode} | {est:.0f} | {peaks} | {sources} | {ratios} | {mix:.3f} | {hp} / {lp} / {shelf:+g} | {db(rms(pcm)/32768):.2f} |')
            check = f'loopcheck_{p.name}'
            checks.append(f'| [{check}](loopcheck/{check}) | {jump} | {maximum} | {pre:.2f} | {post:.2f} | {post-pre:+.2f} |')
            key = (view,mode)
            if key in previous:
                old_rpm, old = previous[key]
                ratio = np.sqrt(rpm/old_rpm)
                diffs = bands(pcm,1/ratio)-bands(old,ratio)
                comparisons.append(f'| {view} / {mode} | {old_rpm}–{rpm} | '+
                                   ' / '.join(f'{d:+.1f}' for d in diffs)+' |')
            previous[key] = (rpm,pcm)
    fx_rows = [effect('door_open',58149,92.46,94.28,(90.1,91.4),145,9300,.012,.115),
               effect('door_close',58149,100.78,102.55,(98.2,99.7),125,8500,.012,.095),
               effect('air_brake_release',96993,0,2.26,(3.6,4.7),260,11000,.004,.18)]
    sections = dict(sources=source_rows, engines=rows, seams=checks, effects=fx_rows, adjacent=comparisons)
    template = Path(__file__).with_name('samples_template.md').read_text()
    for name, table in sections.items():
        template = template.replace('{{'+name+'}}', '\n'.join(table))
    (OUT/'samples.md').write_text(template)


if __name__ == '__main__':
    main()

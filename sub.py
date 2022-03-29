import os
import io
import json
import time
import wave
import numpy
import shutil
import hashlib
import datetime
import requests
import sounddevice

class VoiceAi():
    def _get_hash(self, text):
        m=hashlib.sha1()
        m.update(text.encode("utf-8"))
        return m.hexdigest()

    def _make_path(self, text):
        dir = self._ai_name()
        if not os.path.exists(dir):
            os.mkdir(dir)
        hash = self._get_hash(text) + '.wav'
        path = os.path.join(dir,hash)
        return path

    def _get_cached_wav(self, text):
        path = self._make_path(text)

        if not os.path.exists(path):
            return None
        if os.path.getsize(path) < 1024:
            os.remove(path)
            return None
        with wave.open(path, "r") as wav:
            fs = wav.getframerate()
            wav = numpy.frombuffer(wav.readframes(wav.getnframes()) , dtype= "int16")
            return (wav, fs)

    def _cache_wav(self, text, wav, fs):
        path = self._make_path(text)
        if os.path.exists(path):
            return
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(fs)
            w.writeframes(wav.tobytes())

    def cache_purge(self):
        dir = self._ai_name()
        if os.path.exists(dir):
            shutil.rmtree(dir)

    def generate_wav(self, text):
        ret = self._get_cached_wav(text)
        if ret:
            print('DEBUG: %s is Found. Use cached wav file. path:%s' % (text, self._make_path(text)))
            return ret
        print('DEBUG: %s is Not Found. File will be generated. path:%s' % (text, self._make_path(text)))
        ret = self._generate_wav(text)
        if not ret:
            return None
        (wav, fs) = ret
        self._cache_wav(text, wav, fs)
        return (wav, fs)

    def _ai_name(self) -> str:
         raise NotImplementedError()

    def _generate_wav(self, text):
         raise NotImplementedError()

class VoiceVox(VoiceAi):
    def _ai_name(self):
        return 'VoiceVox'

    ## speaker:2 四国めたん(ノーマル)
    def _generate_wav(self, text, speaker=2):
        host = 'kuwanolabserver.iis.u-tokyo.ac.jp'
        port = 50021
        params = (('text', text),('speaker', speaker),)
        response1 = requests.post(f'http://{host}:{port}/audio_query', params=params )
        headers = {'Content-Type': 'application/json',}
        response2 = requests.post(
            f'http://{host}:{port}/synthesis',
            headers=headers,
            params=params,
            data=json.dumps(response1.json())
        )

        fs = 24000
        wav = numpy.frombuffer(response2.content, numpy.int16)
        return (wav, fs)

class AkaneChan(VoiceAi):
    def _ai_name(self):
        return 'AkaneChan'

    def _get_data_url(self, text) -> str:
        data = {}
        data["api-version"] = "v5"
        data["speaker_id"] = "552"
        data["text"] = text
        data["ext"] = "wav"
        data["volume"] = "1.0"
        data["speed"] = "1.3"
        data["pitch"] = "1.0"
        data["range"] = "1.0"
        data["anger"] = "0.0"
        data["sadness"] = "0.0"
        data["joy"] = "0.0"
        data["callback"] = "callback"
        headers = {}
        headers["content-type"] = "application/x-www-form-urlencoded"
        url = "https://cloud.ai-j.jp/demo/aitalk2webapi_nop.php"
        res = requests.post(url, data=data, headers = headers)
        res = res.text.split('(')[1].split(")")[0]
        return "https:" + json.loads(res)["url"]

    def _download(self, url) -> io.BytesIO:
        bio = io.BytesIO()
        res = requests.get(url, stream=True)
        if res.status_code == 200:
            bio.write(res.content) 
        bio.seek(0)
        return bio

    def _trimmed_wav(self, bio):
        fs = 0
        wav = []
        with wave.open(bio, 'r') as w:
            fs = w.getframerate()
            wav = numpy.frombuffer(w.readframes(w.getnframes()) , dtype= "int16")
        win = int(fs * 0.5)
        step = int(fs / 20)
        for index in range(0, len(wav) - win, step):
            val = numpy.sum(numpy.abs(wav[index:index+win]))
            if val < 1:
                return (wav[index+win: -1], fs)
        return (wav, fs)

    def _generate_wav(self, text):
        url = self._get_data_url(text)
        bio = self._download(url)
        return self._trimmed_wav(bio)

def Talk(text, mode = None):
    ai = VoiceVox()
    if mode and mode == 'kansai':
        ai = AkaneChan()
    (wav, fs) = ai.generate_wav(text)

    sounddevice.play(wav, fs)
    time.sleep(len(wav)/fs + 1.0)

def Talk_Sentence(sentense, mode = None):
    ai = VoiceVox()
    if mode and mode == 'kansai':
        ai = AkaneChan()
    wav = None
    fs = 0
    if type(sentense) is not list:
        sentense = sentense.split(' ')
    for text in sentense:
        (w, fs) = ai.generate_wav(text)
        if wav is None:
            wav = w
        else:
            wav = numpy.concatenate([wav, w], 0)

    sounddevice.play(wav, fs)
    time.sleep(len(wav)/fs + 1)

class klab:
    # 今日のログイン者の情報を取得します
    def _get_json(self):
        ## 内部参照用URL
        #url = "http://kuwanolabserver.iis.u-tokyo.ac.jp:28080/api/today_list"
        # 外部参照用URL
        url = "https://kuwano:Mountaineering1114@www.geo.mydns.jp/record/api/today_list"
        headers = {"content-type": "application/json"}
        r = requests.get(url, headers=headers)
        data = r.json()
        return data

    # ログインの最初と最後を判別します
    def _find_enter_exit_time(self, list):
        enter = exit = None
        # 最初と最後のタッチを判別する
        for item in list:
            item = datetime.datetime.strptime(item, '%Y-%m-%d %H:%M:%S')
            if enter is None:
                enter = item
            elif enter > item:
                enter = item
            if exit is None:
                exit = item
            elif exit < item:
                exit = item
        if enter is not None and exit is not None:
            diff_min = (exit - enter).total_seconds() / 60
            if diff_min < 5:
                exit = None
        return (enter, exit)

    # 初期化処理
    def __init__(self, debug = False):
        self._check_dict = {}
        self._prev_datetime = datetime.datetime.now()
        # 起動時にチェックをして読み捨てることで
        # しゃべり続けるのを防止
        if debug is False:
            self.check()

    # 入退出者を確認します
    # 返り値はそれぞれlist型です
    # ノータイムで連続して呼び出さないようにしてください
    def check(self):
        enter_name_list = []
        exit_name_list = []
        now = datetime.datetime.now()

        # 日付が越えてないかチェック
        if now.day != self._prev_datetime.day:
            # 越えていれば初期化
            self._prev_datetime = now
            self._check_dict = {}

        # 差分をチェック
        json = self._get_json()
        name_list = list(json.keys())
        for name in name_list:
            dt_list = json[name]
            (enter, exit) = self._find_enter_exit_time(dt_list)

            # もし一度もチェックされていない場合
            if name not in self._check_dict:
                self._check_dict[name] = {}
                if enter is not None:
                    enter_name_list.append(name)
                    self._check_dict[name]["enter"] = True
                if exit is not None:
                    exit_name_list.append(name)
                    self._check_dict[name]["exit"] = True
            # 2回目以降のチェックの場合
            else:
                if enter is not None and self._check_dict[name].get("enter") is None:
                    enter_name_list.append(name)
                    self._check_dict[name]["enter"] = True
                if exit is not None and  self._check_dict[name].get("exit") is None:
                    exit_name_list.append(name)
                    self._check_dict[name]["exit"] = True

        return (enter_name_list, exit_name_list)

    # デバッグ用関数です
    # 適当な名前を適当に返します
    def debug_check(self):
        import random
        prob = 0.97
        enter_name_list = []
        exit_name_list = []
        name_list = ['Reiko Kuwano', 'Masahide Otsubo', 'Makoto Kuno', 'Satoko Kichibayashi', 'Eiko Yoshimoto', 'Itsuki Sato', 'Chitravel Sanjei', 'Li Yang', 'Liu Junming', 'Naqi Ali', 'Daichi Yokoyama', 'Yohei Karasaki', 'Chhoeur Pryalen', 'Yutaro Hara', 'Koki Horinouchi', 'Rawiwan']
        for name in name_list:
            if prob < random.random():
                enter_name_list.append(name)
            if prob < random.random():
                exit_name_list.append(name)
        return (enter_name_list, exit_name_list)

def ai_mode(eng):
    list = ['Daichi Yokoyama', 'Yohei Karasaki', 'Koki Horinouchi', 'Hiroyuki Hashimoto']
    if eng in list:
        return 'kansai'
    return ''

def enter_message():
    now = datetime.datetime.now()
    if now.hour < 11:
        return 'おはようございます'
    if now.hour < 17:
        return 'こんにちは'
    return 'こんばんは'

def convert_eng2jpn_name(eng):
    if 'Kuwano' in eng:
        return 'クワノ先生'
    if 'Otsubo' in eng:
        return 'オオツボ先生'
    if 'Kuno' in eng:
        return 'クノさん'
    if 'Kichibayashi' in eng:
        return 'キチバヤシさん'
    if 'Yoshimoto' in eng:
        return 'ヨシモトさん'
    if 'Itsuki' in eng:
        return 'イツキくん'
    if 'Sanjei' in eng:
        return 'サンジェイさん'
    if 'Yang' in eng:
        return 'ヤンさん'
    if 'Junming' in eng:
        return 'シュンメイさん'
    if 'Naqi Ali' in eng:
        return 'アリさん'
    if 'Yokoyama' in eng:
        return 'よこやん'
    if 'Karasaki' in eng:
        return 'ちゃんから'
    if 'Pryalen' in eng:
        return 'レンさん'
    if 'Hara':
        return 'ハラさん'
    if 'Horinouchi':
        return 'のうち'
    if 'Rawiwan':
        return 'ライワンさん'
    if 'Hashimoto':
        return 'ハシモトくん'

def Mainloop():
    print('pid:' + str(os.getpid()))
    print("Ctrl+Cで終了します")

    k = klab()

    while True:
        (enter, exit) = k.check()
        num_event = len(enter) + len(exit)
        if num_event < 1:
            time.sleep(1)
            continue
        for name in enter:
            jpn_name = convert_eng2jpn_name(name)
            mode = ai_mode(name)
            message = enter_message()
            Talk_Sentence([jpn_name, message], mode)
            time.sleep(1)

        for name in exit:
            jpn_name = convert_eng2jpn_name(name)
            mode = ai_mode(name)
            message = 'お疲れ様でした'
            Talk_Sentence([jpn_name, message], mode)
            time.sleep(1)

if __name__ == '__main__':
    #Mainloop()
    #Talk_Sentence(['やめて！ラーの翼神竜の特殊能力で、ギルフォード・ザ・ライトニングを焼き払われたら、闇のゲームでモンスターと繋がってる城之内の精神まで燃え尽きちゃう！','お願い、死なないで城之内！あんたが今ここで倒れたら、舞さんや遊戯との約束はどうなっちゃうの？ ライフはまだ残ってる。ここを耐えれば、マリクに勝てるんだから！', '次回、「城之内死す」', 'デュエルスタンバイ！'])
    Talk('そうはならんやろ', 'kansai')

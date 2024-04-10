import threading
from queue import Queue, Full

import pyaudio

from janim.utils.config import Config


class AudioPlayer:
    def __init__(self):
        self.framerate = Config.get.audio_framerate

        self.thread: threading.Thread | None = None
        self.queue: Queue = Queue(maxsize=1)

    def write(self, data: bytes):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

        try:
            self.queue.put(data, block=False)
        except Full:
            pass

    def _run(self):
        p = pyaudio.PyAudio()

        self.stream = p.open(format=pyaudio.paInt16,
                             channels=1,
                             rate=self.framerate,
                             output=True)

        while True:
            data = self.queue.get()
            self.stream.write(data)

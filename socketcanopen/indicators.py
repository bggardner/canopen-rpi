import can
from .constants import *

class Indicator:
    OFF = {'DutyCycle': 0, 'Frequency': 2.5}
    FLASH1 = {'DutyCycle': 16.67, 'Frequency': 0.833}
    #FLASH2 = {} Cannot accomplish with PWM
    #FLASH3 = {} Cannot accomplish with PWM
    BLINK = {'DutyCycle': 50, 'Frequency': 2.5}
    FLICKER = {'DutyCycle': 50, 'Frequency': 10}
    ON = {'DutyCycle': 100, 'Frequency': 2.5}

    def __init__(self, channel, init_state):
        import RPi.GPIO as GPIO
        GPIO.setup(channel, GPIO.OUT)
        self._pwm = GPIO.PWM(channel, init_state.get('Frequency'))
        self._pwm.start(init_state.get('DutyCycle'))

    def set_state(self, state):
        self._pwm.ChangeDutyCycle(state.get('DutyCycle'))
        self._pwm.ChangeFrequency(state.get('Frequency'))


class ErrorIndicator(Indicator):
    def __init__(self, channel, init_state=can.BusState.BUS_OFF, interval=1):
        init_state = self._get_state(init_state)
        self.interval = interval
        super().__init__(channel, init_state)

    def _get_state(self, err_state):
        if err_state == can.BusState.ERROR_ACTIVE:
            indicator_state = self.OFF
        elif err_state == can.BusState.ERROR_PASSIVE:
            indicator_state = self.FLASH1
        else: # BUS-OFF or UNKNOWN
            indicator_state = self.ON
        return indicator_state

    def set_state(self, err_state):
        indicator_state = self._get_state(err_state)
        super().set_state(indicator_state)


class RunIndicator(Indicator):
    def __init__(self, channel, init_state=NMT_STATE_INITIALISATION):
        init_state = self._get_state(init_state)
        super().__init__(channel, init_state)

    def _get_state(self, nmt_state):
        if nmt_state == NMT_STATE_PREOPERATIONAL:
            indicator_state = self.BLINK
        elif nmt_state == NMT_STATE_OPERATIONAL:
            indicator_state = self.ON
        elif nmt_state == NMT_STATE_STOPPED:
            indicator_state = self.FLASH1
        else:
            indicator_state = self.OFF
        return indicator_state

    def set_state(self, nmt_state):
        indicator_state = self._get_state(nmt_state)
        super().set_state(indicator_state)

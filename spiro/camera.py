import time
from spiro.logger import log, debug

class OldCamera:
    def __init__(self):
        debug('Legacy camera stack detected.')
        self.camera = PiCamera()
        self.type = 'legacy'
        # cam.framerate dictates longest exposure (1/cam.framerate)
        try:
            # use attribute on the camera instance consistently
            self.camera.framerate = 5
            self.camera.iso = 50
        except Exception:
            # be tolerant if attributes are missing on some stacks
            pass

        # set to MAX_RESOLUTION if available, otherwise leave default
        try:
            if hasattr(self.camera, 'MAX_RESOLUTION'):
                self.camera.resolution = self.camera.MAX_RESOLUTION
        except Exception:
            pass

        try:
            self.camera.rotation = 90
        except Exception:
            pass

        try:
            self.camera.image_denoise = False
        except Exception:
            # some camera stacks may not support this attribute
            pass

        try:
            # meter_mode may be named differently; protect against missing attr
            self.camera.meter_mode = 'spot'
        except Exception:
            pass

    def start_stream(self, output):
        # use a tuple for resolution where supported
        try:
            self.camera.resolution = (2592, 1944)
        except Exception:
            pass
        self.camera.start_recording(output, format='mjpeg', resize='1024x768')

    def stop_stream(self):
        self.camera.stop_recording()
        try:
            if hasattr(self.camera, 'MAX_RESOLUTION'):
                self.camera.resolution = self.camera.MAX_RESOLUTION
        except Exception:
            pass

    @property
    def zoom(self):
        return getattr(self.camera, 'zoom', None)

    @zoom.setter
    def zoom(self, value):
        # expect a single value (tuple) per property setter protocol
        try:
            self.camera.zoom = value
        except Exception:
            raise

    def auto_exposure(self, value):
        if value:
            self.camera.shutter_speed = 0
            self.camera.exposure_mode = "auto"
            self.camera.iso = 0
        else:
            self.camera.exposure_mode = "off"

    def capture(self, obj, format='png'):
        self.camera.capture(obj, format=format)

    @property
    def shutter_speed(self):
        return self.camera.shutter_speed

    @property
    def iso(self):
        return self.camera.iso

    @iso.setter
    def iso(self, value):
        self.camera.iso = value

    def close(self):
        try:
            self.camera.close()
        except Exception:
            pass


class NewCamera:
    def __init__(self):
        debug('Libcamera detected.')
        self.camera = Picamera2()
        self.type = 'libcamera'
        self.streaming = False
        self.stream_output = None

        self.still_config = self.camera.create_still_configuration(main={"size": (4608, 3456)}, lores={"size": (320, 240)})
        self.video_config = self.camera.create_video_configuration(main={"size": (1024, 768)})
        try:
            self.camera.configure(self.video_config)
        except Exception:
            pass

        # camera_controls may vary; attempt to get lens limits if present
        try:
            controls_map = getattr(self.camera, 'camera_controls', {})
            self.lens_limits = controls_map.get('LensPosition', None)
        except Exception:
            self.lens_limits = None

        try:
            self.camera.set_controls({
                'NoiseReductionMode': controls.draft.NoiseReductionModeEnum.Off,
                'AeMeteringMode': controls.AeMeteringModeEnum.Spot,
                "AfMode": controls.AfModeEnum.Manual,
                "LensPosition": (self.lens_limits[2] if self.lens_limits and len(self.lens_limits) > 2 else 0)
            })
        except Exception:
            # be lenient if controls or enums are not available
            pass

        try:
            self.camera.start()
        except Exception:
            pass

    def start_stream(self, output):
        log('Starting stream.')
        try:
            self.stream_output = output
            self.streaming = True
            self.camera.switch_mode(self.video_config)
            self.camera.start_recording(MJPEGEncoder(), FileOutput(output))
        except Exception:
            debug('Failed to start stream', exc_info=True)

    def stop_stream(self):
        # intentionally a no-op for libcamera in this design
        pass

    @property
    def zoom(self):
        # not implemented for libcamera wrapper
        return None

    @zoom.setter
    def zoom(self, value):
        """Accepts a tuple (x, y, w, h) where values are fractions of the full sensor size."""
        try:
            x, y, w, h = value
        except Exception:
            raise ValueError('zoom setter expects a tuple (x, y, w, h)')

        try:
            (resx, resy) = self.camera.camera_properties.get('PixelArraySize', (0, 0))
            self.camera.set_controls({"ScalerCrop": (int(x * resx), int(y * resy), int(w * resx), int(h * resy))})
        except Exception:
            debug('Failed to set zoom', exc_info=True)

    def auto_exposure(self, value):
        try:
            self.camera.set_controls({'AeEnable': value})
        except Exception:
            debug('Failed to set auto_exposure', exc_info=True)

    def capture(self, obj, format='png'):
        stream = self.streaming

        log('Capturing image.')
        try:
            self.camera.switch_mode(self.still_config)
            self.camera.capture_file(obj, format=format)
            log('Ok.')
        except Exception:
            debug('Capture failed', exc_info=True)

        if stream:
            self.start_stream(self.stream_output)

    @property
    def shutter_speed(self):
        try:
            return self.camera.capture_metadata().get('ExposureTime')
        except Exception:
            return None

    @shutter_speed.setter
    def shutter_speed(self, value):
        try:
            self.camera.set_controls({"ExposureTime": value})
        except Exception:
            debug('Failed to set shutter_speed', exc_info=True)

    @property
    def iso(self):
        try:
            return int(self.camera.capture_metadata().get('AnalogueGain', 1) * 100)
        except Exception:
            return None

    @iso.setter
    def iso(self, value):
        try:
            self.camera.set_controls({"AnalogueGain": value / 100})
        except Exception:
            debug('Failed to set iso', exc_info=True)

    def close(self):
        try:
            self.camera.close()
        except Exception:
            pass

    def still_mode(self):
        try:
            self.camera.switch_mode(self.still_config)
        except Exception:
            pass

    def video_mode(self):
        try:
            self.camera.switch_mode(self.video_config)
        except Exception:
            pass

    @property
    def resolution(self):
        # best-effort: return still resolution if available
        return (4608, 3456)

    @resolution.setter
    def resolution(self, res):
        # not implemented for libcamera wrapper here
        pass

    @property
    def awb_mode(self):
        return None

    @awb_mode.setter
    def awb_mode(self, mode):
        pass

    @property
    def awb_gains(self):
        return None

    @awb_gains.setter
    def awb_gains(self, gains):
        pass

    def focus(self, val):
        try:
            self.camera.set_controls({'LensPosition': val})
        except Exception:
            debug('Failed to set focus', exc_info=True)


try:
    from picamera import PiCamera
    try:
        cam
    except NameError:
        cam = OldCamera()
except Exception:
    from picamera2 import Picamera2
    from picamera2.outputs import FileOutput
    from picamera2.encoders import MJPEGEncoder
    from libcamera import controls
    try:
        cam
    except NameError:
        cam = NewCamera()
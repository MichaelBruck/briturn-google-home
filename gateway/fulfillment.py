"""Google Cloud-to-cloud JSON mapping, independent of network transport."""
PREFIX = 'action.devices.'


class InvalidCommand(ValueError):
    def __init__(self, code):
        self.code = code


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise InvalidCommand('valueOutOfRange')
    return value


def operation(execution):
    command, params = execution.get('command'), execution.get('params', {})
    if not isinstance(params, dict):
        raise InvalidCommand('protocolError')
    if command == PREFIX + 'commands.OnOff':
        if type(params.get('on')) is not bool:
            raise InvalidCommand('valueOutOfRange')
        return 'on', params['on']
    if command == PREFIX + 'commands.BrightnessAbsolute':
        return 'brightness', integer(params.get('brightness'), 0, 100)
    if command == PREFIX + 'commands.ColorAbsolute':
        color = params.get('color', {})
        if not isinstance(color, dict):
            raise InvalidCommand('protocolError')
        keys = set(color) & {'temperature', 'spectrumRGB', 'spectrumHSV'}
        if keys == {'temperature'}:
            return 'temperature', integer(color['temperature'], 2700, 6500)
        if keys == {'spectrumRGB'}:
            return 'rgb', integer(color['spectrumRGB'], 0, 0xFFFFFF)
    raise InvalidCommand('functionNotSupported')


def nonempty_list(value, limit):
    if not isinstance(value, list) or not 1 <= len(value) <= limit:
        raise InvalidCommand('protocolError')
    return value


def handle(message, backend, owner, revoke):
    request_id = message.get('requestId', '') if isinstance(message, dict) else ''
    response = {'requestId': request_id}
    try:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 256:
            raise InvalidCommand('protocolError')
        inputs = nonempty_list(message.get('inputs'), 1)
        intent = inputs[0]['intent']
        payload = inputs[0].get('payload', {})
        if intent == PREFIX + 'SYNC':
            response['payload'] = {'agentUserId': owner, 'devices': [
                {'id': key, 'type': PREFIX + 'types.LIGHT',
                 'traits': [PREFIX + 'traits.' + t for t in ('OnOff', 'Brightness', 'ColorSetting')],
                 'name': {'name': d['name']}, 'willReportState': False,
                 'attributes': {'colorModel': 'rgb', 'colorTemperatureRange': {
                     'temperatureMinK': 2700, 'temperatureMaxK': 6500}},
                 'deviceInfo': {'manufacturer': 'SKY-TOUCH / Briturn compatible',
                                'model': 'AK001-ZJ21413 / 0x35 RGBCW'}}
                for key, d in backend.devices.items()]}
        elif intent == PREFIX + 'QUERY':
            states = {}
            for device in nonempty_list(payload.get('devices'), 2):
                key = device['id']
                if key not in backend.devices:
                    states[key] = {'online': False, 'status': 'ERROR', 'errorCode': 'deviceNotFound'}
                    continue
                try:
                    states[key] = backend.read(key)
                    states[key]['status'] = 'SUCCESS'
                except (OSError, ValueError):
                    states[key] = {'online': False, 'status': 'OFFLINE'}
            response['payload'] = {'devices': states}
        elif intent == PREFIX + 'EXECUTE':
            # Validate the entire batch before the first physical write.
            plan = []
            for group in nonempty_list(payload.get('commands'), 4):
                ids = [d['id'] for d in nonempty_list(group.get('devices'), 2)]
                if any(key not in backend.devices for key in ids):
                    raise InvalidCommand('deviceNotFound')
                ops = [operation(e) for e in nonempty_list(group.get('execution'), 4)]
                plan.extend((key, ops) for key in ids)
            results = []
            for key, ops in plan:
                try:
                    results.append({'ids': [key], 'status': 'SUCCESS',
                                    'states': backend.execute(key, ops)})
                except PermissionError:
                    results.append({'ids': [key], 'status': 'ERROR', 'errorCode': 'notSupported'})
                except (OSError, ValueError):
                    results.append({'ids': [key], 'status': 'ERROR', 'errorCode': 'deviceOffline'})
            response['payload'] = {'commands': results}
        elif intent == PREFIX + 'DISCONNECT':
            revoke()
            return {}
        else:
            raise InvalidCommand('notSupported')
    except InvalidCommand as exc:
        response['payload'] = {'errorCode': exc.code}
    except (KeyError, TypeError, AttributeError):
        response['payload'] = {'errorCode': 'protocolError'}
    return response

"""Decode observed WeCom 5.0.12 face-to-face records without OCR or UI input."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import re

LOCAL_TZ = timezone(timedelta(hours=8))


def _varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data):
            raise ValueError('Truncated protobuf varint')
        byte = data[pos]
        pos += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, pos
    raise ValueError('Oversized protobuf varint')


def decode_fields(data):
    result = defaultdict(list)
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ValueError('Invalid protobuf field')
        if wire == 0:
            value, pos = _varint(data, pos)
        else:
            if wire == 2:
                length, pos = _varint(data, pos)
            elif wire in (1, 5):
                length = 8 if wire == 1 else 4
            else:
                raise ValueError('Unsupported protobuf wire type')
            if length > len(data) - pos:
                raise ValueError('Truncated protobuf field')
            value = data[pos:pos + length]
            pos += length
        result[number].append(value)
    return dict(result)


def _single(fields, number, default=None):
    values = fields.get(number, [])
    if not values:
        return default
    if len(values) != 1:
        raise ValueError(f'Unexpected repeated protobuf field {number}')
    return values[0]


def decode_text(blob):
    value = blob
    for number in (8, 1, 2, 1):
        value = _single(decode_fields(value), number)
        if not isinstance(value, bytes):
            raise ValueError('Unexpected native text payload shape')
    return value.decode('utf-8', errors='strict')


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp, LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')


def room_catalog(conn):
    rooms = []
    for row in conn.execute('SELECT room_id, MIN(send_time) AS started, MAX(send_time) AS updated, COUNT(*) AS cached_rows FROM voice_room_message GROUP BY room_id ORDER BY started DESC'):
        room = dict(row)
        room['title'] = format_time(room['started']) + ' 面聊'
        for item in conn.execute('SELECT blob FROM voice_room_message WHERE room_id=? AND content_type=2386 ORDER BY rid', (room['room_id'],)):
            body = _single(decode_fields(item['blob']), 8)
            if not isinstance(body, bytes):
                continue
            label = _single(decode_fields(body), 10)
            if isinstance(label, bytes):
                match = re.search('修改面聊名称为[“「](.*)[”」]', label.decode('utf-8'))
                if match:
                    room['title'] = match.group(1)
        rooms.append(room)
    return rooms


def extract_room(conn, room_id, aliases=None):
    aliases = aliases or {}
    records, events, missing, unresolved, skipped_types = [], [], [], {}, defaultdict(int)
    previous = 0
    session = 1
    ended = False
    excluded = 0
    for row in conn.execute('SELECT * FROM voice_room_message WHERE room_id=? ORDER BY rid', (room_id,)):
        rid = row['rid']
        if rid > previous + 1:
            missing.append([previous + 1, rid - 1])
        previous = rid
        parsed = decode_fields(row['blob'])
        state = _single(parsed, 13, 0)
        if not isinstance(state, int):
            raise ValueError('Invalid native record state')
        marker = _single(parsed, 15, b'').decode('utf-8')
        if state != 0:
            if row['content_type'] == 2:
                excluded += 1
            continue
        if marker.startswith('restart_voice_room_tips_'):
            session += 1
            ended = False
            events.append({'type': 'resumed', 'timestamp': row['send_time'], 'session': session})
        if marker.startswith('voice_room_end_'):
            ended = True
            events.append({'type': 'ended', 'timestamp': row['send_time'], 'session': session})
        if row['content_type'] != 2:
            skipped_types[row['content_type']] += 1
            continue
        text = decode_text(row['blob'])
        speaker = row['sender_name']
        if not speaker:
            sender = str(row['sender'])
            if sender in aliases:
                speaker = aliases[sender]
            else:
                if sender not in unresolved:
                    unresolved[sender] = f'成员{len(unresolved) + 1}'
                speaker = unresolved[sender]
        records.append({'speaker': speaker, 'timestamp': row['send_time'], 'time': format_time(row['send_time']),
                        'text': text, 'session': session, 'native_id': rid})
    if not records:
        raise ValueError('No supported transcript text in this cached room')
    return {'records': records, 'events': events, 'missing_id_ranges': missing,
            'last_segment_ended': ended, 'excluded_nonzero_state': excluded,
            'unresolved_speakers': unresolved, 'non_text_record_types': dict(skipped_types),
            'source': 'local WeCom voice-room database snapshot; server completeness not asserted'}


def render_markdown(title, result):
    records = result['records']
    lines = [f'# {title}', '', f'> 本机缓存原始转录 · {len(records)} 条 · UTC+08:00',
             '> 正文直接读取企业微信数据库，未使用 OCR 或重新转录。', '']
    if result['missing_id_ranges'] or not result['last_segment_ended']:
        lines += ['> 注意：缓存存在序号缺口，或尚未观察到最后一段结束标记；不能确认完整。', '']
    if result['unresolved_speakers']:
        lines += ['> “成员N”表示数据库中未附带显示姓名的已识别成员；同一编号在本文中指同一人。', '']
    if result['excluded_nonzero_state']:
        lines += [f'> 已排除 {result["excluded_nonzero_state"]} 条非正常状态的原生记录；详见 JSON 报告。', '']
    current = None
    for record in records:
        if current != record['session']:
            current = record['session']
            lines += [f'## 第 {current} 段 · {record["time"]}', '']
        lines += [f'### {record["time"]} · {record["speaker"]}', '', record['text'], '']
    return '\n'.join(lines)

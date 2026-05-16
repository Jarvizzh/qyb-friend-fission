import json
import requests
import websocket
import time
import random
import uuid
import traceback
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from .qyb_client import BASE_URL, HEADERS
from .. import models
from ..database import SessionLocal

def get_wechat_accounts(session_id):
    api_url = f"{BASE_URL}/api/wechat/list?page=1&page_size=999"
    response = requests.get(api_url, cookies={'PHPSESSID': session_id}, headers=HEADERS)
    res_data = response.json()
    if res_data.get('errcode') != 0:
        raise Exception(f"获取账号列表失败: {res_data.get('errmsg', '未知错误')}")
    accounts_map = {}
    for item in res_data.get('data', []):
        nickname = item.get('nickname')
        corp_name = item.get('corp_name', '企业微信')
        display_name = f"{nickname}@{corp_name}" if corp_name else nickname
        accounts_map[display_name] = {
            "wxid": item.get('wxid'),
            "nickname": nickname,
            "avatar": item.get('avatar', ''),
            "corp_wxid": item.get('corp_wxid', ''),
            "corp_name": corp_name
        }
    return accounts_map

def get_customer_by_name(session_id, rel_wxid, receiver_name, receiver_wxid, prefix=""):
    api_url = f"{BASE_URL}/api/wechat/contacts"
    payload = {"rel_wxid": rel_wxid, "page": 1, "page_size": 100, "search": receiver_name}
    response = requests.post(api_url, json=payload, cookies={'PHPSESSID': session_id}, headers=HEADERS)
    res_data = response.json()
    if 'data' in res_data and res_data['data']:
        for item in res_data['data']:
            if item.get('wxid') == receiver_wxid or item.get('nickname') == receiver_name:
                return item
    return None

def get_tag_id_by_name(session_id, tag_name):
    api_url = f"{BASE_URL}/api/module_tag/list?module=47,52,53,54,55,96,97&page=1&page_size=999&type=2&with_tags=1"
    response = requests.get(api_url, cookies={'PHPSESSID': session_id}, headers=HEADERS)
    res_data = response.json()
    
    def search_id(data):
        if isinstance(data, list):
            for item in data:
                res = search_id(item)
                if res: return res
        elif isinstance(data, dict):
            if data.get('name') == tag_name and 'id' in data:
                return data['id']
            for key, val in data.items():
                res = search_id(val)
                if res: return res
        return None
    return search_id(res_data)

def get_customers_by_tag(session_id, rel_wxid, tag_id, page_size=50):
    api_url = f"{BASE_URL}/api/wechat/contacts"
    page = 1
    all_customers = []
    while True:
        payload = {
            "rel_wxid": rel_wxid,
            "page": page,
            "page_size": page_size,
            "include_params": {"smart_tag": {"match_type": "1", "ids": [tag_id]}}
        }
        response = requests.post(api_url, json=payload, cookies={'PHPSESSID': session_id}, headers=HEADERS)
        res_data = response.json()
        if 'data' not in res_data or not res_data['data']: break
        for item in res_data['data']:
            all_customers.append({
                "wxid": item.get("wxid", ""),
                "nickname": item.get("nickname", ""),
                "avatar": item.get("avatar", ""),
                "corp_wxid": item.get("corp_wxid", ""),
                "corp_name": item.get("corp_name") or "微信"
            })
        if len(res_data['data']) < page_size: break
        page += 1
        time.sleep(0.5)
    return all_customers

def get_ws_url(session_id):
    api_url = f"{BASE_URL}/api/config/ws"
    response = requests.get(api_url, cookies={'PHPSESSID': session_id}, headers=HEADERS)
    data = response.json()
    if data.get('errcode') == 0:
        return data['data']['url']
    raise Exception(f"获取WS地址失败: {data.get('errmsg')}")

def send_card_message(ws, config, to_wxid, card_info):
    tmp_id = str(uuid.uuid4())[:12]
    payload = {
        "action": "sendMsg",
        "data": {
            "to_wxid": to_wxid,
            "contents": [{
                "msg_type": "card",
                "content": {
                    "avatar": card_info.get('avatar', ""),
                    "corp_name": card_info.get('corp_name', "微信"),
                    "corp_wxid": card_info.get('corp_wxid', ""),
                    "nickname": card_info.get('nickname', ""),
                    "wxid": card_info.get('wxid', "")
                },
                "tmp_id": tmp_id,
                "from_wxid": config['my_wxid'],
                "to_wxid": to_wxid
            }],
            "extra": {"source": 2, "kf_sub_uid": 0}
        },
        "router": {"client": "wechat", "wxid": config['my_wxid'], "uid": config['uid']}
    }
    ws.send(json.dumps(payload))

def process_single_subtask(task, session_id, uid, accounts_map, log, stop_event):
    sender_name = task['sender']
    receiver_name = task['receiver']
    tag_name = task['tag']
    is_internal = task.get('internal', False)
    skip_count = max(0, task.get('start', 1) - 1)
    limit_count = task.get('limit', -1)
    
    prefix = f"[{sender_name} -> {receiver_name}] "
    log(f"{prefix}正在准备子任务 (起始位置: {task.get('start', 1)})...")
    
    try:
        # 解析发送人和接收人
        sender_info = None
        for nickname, info in accounts_map.items():
            if sender_name in nickname or sender_name == info['wxid']:
                sender_info = info
                break
        
        receiver_info = None
        for nickname, info in accounts_map.items():
            if receiver_name in nickname or receiver_name == info['wxid']:
                receiver_info = info
                break
                
        if not sender_info or not receiver_info:
            log(f"{prefix}错误: 未找到发送人或接收人账号。")
            return

        if is_internal:
            receiver_wxid = receiver_info['wxid']
        else:
            receiver_resp = get_customer_by_name(session_id, sender_info['wxid'], receiver_name, receiver_info['wxid'])
            if not receiver_resp:
                log(f"{prefix}错误: 未在通讯录中搜索到接收人详情。")
                return
            receiver_wxid = receiver_resp.get("wxid")

        tag_id = get_tag_id_by_name(session_id, tag_name)
        if not tag_id:
            log(f"{prefix}错误: 未找到标签【{tag_name}】")
            return
            
        cards = get_customers_by_tag(session_id, sender_info['wxid'], str(tag_id))
        if skip_count > 0: cards = cards[skip_count:]
        if limit_count >= 0: cards = cards[:limit_count]
        
        if not cards:
            log(f"{prefix}无名片可发送。")
            return
            
        log(f"{prefix}开始发送 {len(cards)} 张名片...")
        
        BATCH_SIZE = 30
        config = {"my_wxid": sender_info['wxid'], "uid": uid}
        
        for i in range(0, len(cards), BATCH_SIZE):
            if stop_event.is_set(): break
            batch = cards[i : i + BATCH_SIZE]
            ws_url = get_ws_url(session_id)
            ws = websocket.create_connection(ws_url, header=["Origin: https://tool.miaokol.com", f"Cookie: PHPSESSID={session_id}"])
            try:
                for j, card in enumerate(batch):
                    if stop_event.is_set(): break
                    log(f"{prefix}[{i+j+1}/{len(cards)}] 正在发送【{card['nickname']}】")
                    send_card_message(ws, config, receiver_wxid, card)
                    time.sleep(random.randint(3, 5))
            finally:
                ws.close()
                if i + BATCH_SIZE < len(cards): time.sleep(2)
        
        if not stop_event.is_set():
            log(f"{prefix}✅ 该员工所有名片发送完成（共 {len(cards)} 张）")
            
    except Exception as e:
        log(f"{prefix}运行时出错: {str(e)}")

def run_fission_task(task_id, tasks_list, session_id, uid, log_queue, stop_event, concurrency=4):
    def log(msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        full_msg = f"[{timestamp}] {msg}"
        log_queue.put(full_msg)

    try:
        log(f"🚀 任务 {task_id} 启动，采用 {concurrency} 路并发处理...")
        log("------------------------------------------")
        log(f"📊 待处理子任务总数: {len(tasks_list)}")
        for idx, t in enumerate(tasks_list):
            int_str = " (内部)" if t.get('internal') else ""
            log(f"  > 子任务 [{idx+1}]: {t['sender']} -> {t['receiver']}{int_str} | 标签: {t['tag']} | 起始: {t.get('start', 1)} | 数量: {t['limit'] if t['limit'] != -1 else '全部'}")
        log("------------------------------------------")
        
        accounts_map = get_wechat_accounts(session_id)
        
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(process_single_subtask, task, session_id, uid, accounts_map, log, stop_event) 
                for task in tasks_list
            ]
            
            # 等待所有任务完成或被停止
            for future in as_completed(futures):
                if stop_event.is_set():
                    break
                try:
                    future.result()
                except Exception as e:
                    log(f"❌ 子线程执行异常: {str(e)}")

        if stop_event.is_set():
            log(f"🛑 任务 {task_id} 已由用户强制停止。")
        else:
            log(f"✅ 任务 {task_id} 所有子任务执行完毕。")
            
    except Exception as e:
        log(f"❌ 任务全局出错: {str(e)}\n{traceback.format_exc()}")
    finally:
        log_queue.put(None) # 结束信号
        # 强制更新数据库状态，确保状态准确性
        db = SessionLocal()
        try:
            task_rec = db.query(models.TaskRecord).filter(models.TaskRecord.id == task_id).first()
            if task_rec:
                if stop_event.is_set():
                    task_rec.status = "stopped"
                else:
                    task_rec.status = "completed"
                task_rec.completed_at = datetime.datetime.utcnow()
                db.commit()
        except Exception as db_err:
            print(f"Error updating task status in background: {db_err}")
        finally:
            db.close()

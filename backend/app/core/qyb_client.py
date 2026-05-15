import requests

BASE_URL = "https://tool.miaokol.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://tool.miaokol.com",
    "Accept": "application/json, text/plain, */*"
}

def login_qyb(mobile, password):
    """模拟登录获取最新的 Cookie"""
    api_url = f"{BASE_URL}/api/user/signin"
    payload = {"mobile": mobile, "password": password}
    
    session = requests.Session()
    response = session.post(api_url, json=payload, headers=HEADERS)
    res_data = response.json()
    
    if res_data.get('errcode') == 0:
        new_cookie = session.cookies.get('PHPSESSID')
        if new_cookie:
            # 登录成功后立即拉取一次 authInfo 以获取 UID
            uid = None
            try:
                auth_res = session.get(f"{BASE_URL}/api/user/authInfo", headers=HEADERS)
                auth_data = auth_res.json()
                uid = auth_data.get('data', {}).get('id')
                if uid:
                    uid = str(uid)
            except:
                pass
            return new_cookie, uid
        else:
            raise Exception("登录接口调用成功，但未能在响应中找到 PHPSESSID。")
    else:
        raise Exception(f"登录失败: {res_data.get('errmsg', '未知错误')}")

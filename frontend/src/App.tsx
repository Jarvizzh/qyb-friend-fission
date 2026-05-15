import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Upload, Play, Square, Download, UserCheck, Terminal, Trash2, Key, ShieldCheck, LogOut, Info, CheckCircle, AlertCircle, XCircle } from 'lucide-react';
import './App.css';
import type { TaskPreview, UserSession } from './types';

// 自动检测 API 地址：开发环境默认 8000 端口，生产环境使用相对路径（由 Nginx 代理）
const API_BASE = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? "http://localhost:8000" : "");
const WS_BASE = (API_BASE || window.location.origin).replace(/^http/, 'ws');

function App() {
  const [toasts, setToasts] = useState<{id: string, message: string, type: 'info' | 'success' | 'error' | 'warning'}[]>([]);
  const addToast = (message: string, type: 'info' | 'success' | 'error' | 'warning' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  };

  const [isVerified, setIsVerified] = useState<boolean | null>(null);
  const [secretKey, setSecretKey] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);

  const [activeTab, setActiveTab] = useState<'auth' | 'task' | 'history'>('auth');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [selectedMobile, setSelectedMobile] = useState('');
  
  const [previewTasks, setPreviewTasks] = useState<TaskPreview[]>([]);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [isTaskRunning, setIsTaskRunning] = useState(false);

  const [historyTasks, setHistoryTasks] = useState<any[]>([]);
  const [historyLogs, setHistoryLogs] = useState<string[]>([]);
  const [showHistoryLogs, setShowHistoryLogs] = useState(false);
  
  const consoleRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const checkAuthStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/auth/check-status`);
      setIsVerified(res.data.is_verified);
    } catch (err) {
      console.error("Check auth status failed", err);
      setIsVerified(false);
    }
  };

  const handleVerifySecret = async () => {
    if (!secretKey) return addToast("请输入系统密钥", "warning");
    setIsVerifying(true);
    try {
      await axios.post(`${API_BASE}/api/auth/verify-secret`, { secret_key: secretKey });
      setIsVerified(true);
      addToast("系统激活成功", "success");
    } catch (err: any) {
      addToast("验证失败: " + (err.response?.data?.detail || err.message), "error");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API_BASE}/api/auth/logout`);
      setIsVerified(false);
      setSecretKey('');
      clearPersistence();
      addToast("已成功退出系统", "info");
    } catch (err) {
      console.error("Logout failed", err);
    }
  };

  useEffect(() => {
    checkAuthStatus();
    fetchSessions();
    const recoverTask = async () => {
      const savedTaskId = localStorage.getItem('currentTaskId');
      const savedPreview = localStorage.getItem('previewTasks');
      const savedMobile = localStorage.getItem('selectedMobile');
      
      if (savedTaskId) {
        try {
          const res = await axios.get(`${API_BASE}/api/tasks/${savedTaskId}/status`);
          if (res.data.is_active) {
            setCurrentTaskId(savedTaskId);
            if (savedPreview) setPreviewTasks(JSON.parse(savedPreview));
            if (savedMobile) setSelectedMobile(savedMobile);
            setIsTaskRunning(true);
            setLogs([]);
            connectWebSocket(savedTaskId);
            setActiveTab('task');
          } else {
            clearPersistence();
          }
        } catch (e) {
          clearPersistence();
        }
      }
    };
    recoverTask();
  }, []);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab]);

  const fetchHistory = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/tasks`);
      setHistoryTasks(res.data);
    } catch (err) {
      console.error("Fetch history failed", err);
    }
  };

  const viewHistoryLogs = async (taskId: string) => {
    try {
      const res = await axios.get(`${API_BASE}/api/tasks/${taskId}/logs`);
      setHistoryLogs(res.data.logs);
      setShowHistoryLogs(true);
    } catch (err) {
      addToast("获取日志失败", "error");
    }
  };

  const deleteHistoryTask = async (taskId: string) => {
    if (!window.confirm("确定要删除这条任务记录吗？此操作不可撤销且会同步删除日志文件。")) return;
    try {
      await axios.delete(`${API_BASE}/api/tasks/${taskId}`);
      fetchHistory();
      addToast("任务已删除", "success");
    } catch (err) {
      addToast("删除失败", "error");
    }
  };

  const downloadHistoryLogs = async (taskId: string) => {
    try {
      const res = await axios.get(`${API_BASE}/api/tasks/${taskId}/logs`);
      const blob = new Blob([res.data.logs.join('\n')], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fission-log-${taskId}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      addToast("下载日志失败", "error");
    }
  };

  const clearPersistence = () => {
    localStorage.removeItem('currentTaskId');
    localStorage.removeItem('previewTasks');
    localStorage.removeItem('selectedMobile');
  };

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const fetchSessions = async () => {
    try {
      const res = await axios.get(`${API_BASE}/api/auth/sessions`);
      setSessions(res.data);
      if (res.data.length > 0) {
        setSelectedMobile(res.data[0].mobile);
      }
    } catch (err) {
      console.error("Fetch sessions failed", err);
    }
  };

  const handleLogin = async () => {
    try {
      await axios.post(`${API_BASE}/api/auth/login`, { mobile, password });
      setMobile('');
      setPassword('');
      fetchSessions();
      addToast("登录授权成功", "success");
    } catch (err: any) {
      addToast("登录失败: " + (err.response?.data?.detail || err.message), "error");
    }
  };

  const handleRevoke = async (mobile: string) => {
    if (!window.confirm(`确定要取消账号 ${mobile} 的授权吗？`)) return;
    try {
      await axios.delete(`${API_BASE}/api/auth/sessions/${mobile}`);
      fetchSessions();
      if (selectedMobile === mobile) setSelectedMobile('');
      addToast("授权已取消", "info");
    } catch (err: any) {
      addToast("取消授权失败: " + (err.response?.data?.detail || err.message), "error");
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(`${API_BASE}/api/tasks/parse-excel`, formData);
      setPreviewTasks(res.data.tasks);
      localStorage.setItem('previewTasks', JSON.stringify(res.data.tasks));
      setActiveTab('task');
      addToast(`成功导入 ${res.data.tasks.length} 条任务`, "success");
    } catch (err: any) {
      addToast("上传失败: " + (err.response?.data?.detail || err.message), "error");
    }
  };

  const startTask = async () => {
    if (!selectedMobile) return addToast("请先选择一个授权账号", "warning");
    if (previewTasks.length === 0) return addToast("请先上传 Excel 任务文件", "warning");

    try {
      const res = await axios.post(`${API_BASE}/api/tasks/start?mobile=${selectedMobile}`, {
        tasks: previewTasks
      });
      const taskId = res.data.task_id;
      setCurrentTaskId(taskId);
      localStorage.setItem('currentTaskId', taskId);
      localStorage.setItem('selectedMobile', selectedMobile);
      localStorage.setItem('previewTasks', JSON.stringify(previewTasks));
      setIsTaskRunning(true);
      setLogs([]);
      connectWebSocket(taskId);
      addToast("裂变任务已启动", "success");
    } catch (err: any) {
      addToast("启动失败: " + (err.response?.data?.detail || err.message), "error");
    }
  };

  const stopTask = async () => {
    if (!currentTaskId) return;
    try {
      await axios.post(`${API_BASE}/api/tasks/${currentTaskId}/stop`);
      clearPersistence();
      setIsTaskRunning(false);
      addToast("任务已强制停止", "info");
    } catch (err: any) {
      addToast("停止失败: " + (err.response?.data?.detail || err.message), "error");
    }
  };

  const connectWebSocket = (taskId: string) => {
    if (wsRef.current) wsRef.current.close();
    
    const ws = new WebSocket(`${WS_BASE}/api/ws/logs/${taskId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      setLogs(prev => [...prev, event.data]);
      if (event.data.includes("任务执行完毕") || event.data.includes("强制停止")) {
        setIsTaskRunning(false);
        clearPersistence();
      }
    };

    ws.onclose = () => {
      console.log("WebSocket closed");
      // 只有在主动识别到结束时才设置 false，避免普通连接断开导致的按钮闪烁
    };
  };

  const downloadLogs = () => {
    const blob = new Blob([logs.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fission-log-${currentTaskId}.txt`;
    a.click();
  };

  return (
    <>
    <div className="container">
      {isVerified === null ? (

        <div style={{display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-purple)'}}>
          <div className="loading-spinner"></div>
          <span style={{marginLeft: '1rem'}}>系统初始化中...</span>
        </div>
      ) : !isVerified ? (
        <div style={{display: 'flex', height: '80vh', alignItems: 'center', justifyContent: 'center'}}>
          <div className="card" style={{width: '100%', maxWidth: '400px', textAlign: 'center', padding: '3rem'}}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%', backgroundColor: 'rgba(168, 85, 247, 0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 2rem'
            }}>
              <Key size={32} color="var(--accent-purple)" />
            </div>
            <h2 style={{marginBottom: '1rem'}}>系统授权验证</h2>
            <p style={{color: 'var(--text-dim)', marginBottom: '2rem', fontSize: '0.9rem'}}>请输入系统密钥以解锁裂变引擎核心功能</p>
            
            <div className="input-group" style={{textAlign: 'left'}}>
              <input 
                type="password" 
                value={secretKey} 
                onChange={e => setSecretKey(e.target.value)} 
                onKeyDown={e => e.key === 'Enter' && handleVerifySecret()}
                placeholder="请输入系统密钥"
                style={{letterSpacing: '0.2em'}}
              />
            </div>
            
            <button 
              className="btn btn-primary" 
              style={{width: '100%', marginTop: '1rem'}} 
              onClick={handleVerifySecret}
              disabled={isVerifying}
            >
              {isVerifying ? '正在验证...' : '立即激活系统'}
            </button>
            
            <div style={{marginTop: '2rem', fontSize: '0.8rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem'}}>
              <ShieldCheck size={14} /> 安全加密验证系统
            </div>
          </div>
        </div>
      ) : (
        <>
          <header className="header">
            <h1 className="title">FISSION ENGINE CORE</h1>
            <div className="status-group">
              {isTaskRunning && <span className="status-badge status-running">● 裂变执行中</span>}
              <button 
                className="btn btn-outline" 
                style={{marginLeft: '1rem', padding: '0.4rem 0.8rem', fontSize: '0.8rem', borderColor: 'rgba(239, 68, 68, 0.3)', color: '#ef4444'}}
                onClick={handleLogout}
              >
                <LogOut size={16} style={{marginRight: '0.4rem'}} /> 退出系统
              </button>
            </div>
          </header>

          <div className="tab-bar">
            <div className={`tab ${activeTab === 'auth' ? 'active' : ''}`} onClick={() => setActiveTab('auth')}>ACCESS AUTH</div>
            <div className={`tab ${activeTab === 'task' ? 'active' : ''}`} onClick={() => setActiveTab('task')}>WORK TERMINAL</div>
            <div className={`tab ${activeTab === 'history' ? 'active' : ''}`} onClick={() => setActiveTab('history')}>TASK HISTORY</div>
          </div>

          {activeTab === 'auth' ? (
            <div className="grid">
              <div className="card">
            <h3><UserCheck size={20} /> 添加账号授权</h3>
            <div className="input-group">
              <label>手机号</label>
              <input type="text" value={mobile} onChange={e => setMobile(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} placeholder="企微宝登录手机号" />
            </div>
            <div className="input-group">
              <label>密码</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleLogin()} placeholder="企微宝登录密码" />
            </div>
            <button className="btn btn-primary" onClick={handleLogin}>立即授权</button>
          </div>

          <div className="card">
            <h3>已授权列表</h3>
            <div style={{maxHeight: '400px', overflowY: 'auto'}}>
              {sessions.map(s => (
                <div key={s.mobile} className="session-item">
                  <div style={{display: 'flex', gap: '1.5rem', alignItems: 'center'}}>
                    <span>账号：{s.mobile}</span>
                    <span style={{color: 'var(--text-dim)', fontSize: '0.9rem'}}>UID：<span style={{color: 'var(--accent-purple)', fontWeight: 600}}>{s.uid}</span></span>
                  </div>
                  <button 
                    className="btn btn-outline" 
                    style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)'}} 
                    onClick={() => handleRevoke(s.mobile)}
                  >
                    <Trash2 size={14} /> 取消授权
                  </button>
                </div>
              ))}
              {sessions.length === 0 && <p style={{color: 'var(--text-dim)', textAlign: 'center', padding: '2rem'}}>暂无授权账号</p>}
            </div>
          </div>
        </div>
      ) : activeTab === 'task' ? (
        <>
          <div className="card">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem'}}>
              <div style={{display: 'flex', gap: '1rem', alignItems: 'center'}}>
                <select 
                  value={selectedMobile} 
                  onChange={e => setSelectedMobile(e.target.value)}
                  style={{width: '300px'}}
                >
                  <option value="">选择企微宝账号</option>
                  {sessions.map(s => <option key={s.mobile} value={s.mobile}>企微宝ID: {s.uid}</option>)}
                </select>
                <label className="btn btn-outline">
                  <Upload size={18} /> 上传 Excel
                  <input type="file" hidden onChange={handleFileUpload} accept=".xlsx,.xls" />
                </label>
              </div>
              <div style={{display: 'flex', gap: '1rem'}}>
                {!isTaskRunning ? (
                  <button className="btn btn-primary" onClick={startTask}>
                    <Play size={18} /> 开始裂变
                  </button>
                ) : (
                  <button className="btn btn-danger" onClick={stopTask}>
                    <Square size={18} /> 强制停止
                  </button>
                )}
                <button className="btn btn-outline" onClick={downloadLogs} disabled={logs.length === 0}>
                   <Download size={18} /> 下载日志
                </button>
              </div>
            </div>

            {previewTasks.length > 0 && (
              <div style={{marginTop: '2rem'}}>
                <h4 style={{color: 'var(--accent-purple)', marginBottom: '1rem'}}>数据预览 ({previewTasks.length} 条任务)</h4>
                <div style={{maxHeight: '300px', overflowY: 'auto', border: '1px solid var(--border-glass)', borderRadius: '8px'}}>
                  <table className="preview-table">
                    <thead>
                      <tr>
                        <th>发送人</th>
                        <th>智能标签</th>
                        <th>接收人</th>
                        <th>接收人是否为内部员工</th>
                        <th>起始位置</th>
                        <th>发送数量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewTasks.map((t, idx) => (
                        <tr key={idx}>
                          <td>{t.sender}</td>
                          <td>{t.tag}</td>
                          <td>{t.receiver}</td>
                          <td>{t.internal ? <span style={{color: 'var(--accent-cyan)'}}>是</span> : '否'}</td>
                          <td>{t.start}</td>
                          <td>{t.limit === -1 ? '全部' : t.limit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <h3 style={{marginBottom: '1.5rem'}}>
              <Terminal size={20} /> 实时控制台
            </h3>
            <div className="console" ref={consoleRef}>
              {logs.map((log, i) => {
                let logClass = "log-info";
                if (log.includes("❌") || log.includes("🛑") || log.includes("错误")) logClass = "log-error";
                else if (log.includes("✅") || log.includes("执行完毕")) logClass = "log-success";
                
                return <div key={i} className={logClass}>{log}</div>;
              })}
              {logs.length === 0 && <div style={{color: 'var(--text-dim)', opacity: 0.5}}>等待任务启动... [SYSTEM READY]</div>}
            </div>
          </div>
        </>
      ) : (
        <div className="card">
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem'}}>
            <h3>任务执行历史</h3>
            <button className="btn btn-outline" onClick={fetchHistory} style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.4rem'}}>
               <Play size={14} /> 刷新列表
            </button>
          </div>

          <div style={{maxHeight: '600px', overflowY: 'auto', border: '1px solid var(--border-glass)', borderRadius: '12px'}}>
            <table className="preview-table">
              <thead>
                <tr>
                  <th>任务 ID</th>
                  <th>状态</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {historyTasks.map(task => (
                  <tr key={task.id}>
                    <td style={{fontSize: '0.8rem', color: 'var(--accent-purple)'}}>{task.id}</td>
                    <td>
                      <span className={`status-badge ${task.status === 'completed' ? 'status-success' : task.status === 'running' ? 'status-running' : 'status-stopped'}`} 
                        style={{border: '1px solid transparent'}}>
                        {task.status === 'completed' ? '已完成' : task.status === 'running' ? '执行中' : '已停止'}
                      </span>
                    </td>
                    <td style={{fontSize: '0.8rem'}}>{new Date(task.created_at).toLocaleString()}</td>
                    <td>
                      <div style={{display: 'flex', gap: '0.5rem'}}>
                        <button className="btn btn-outline" style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem'}} onClick={() => viewHistoryLogs(task.id)}>
                          查看日志
                        </button>
                        <button className="btn btn-outline" style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem'}} onClick={() => downloadHistoryLogs(task.id)}>
                          下载日志
                        </button>
                        <button className="btn btn-outline" style={{padding: '0.4rem 0.8rem', fontSize: '0.8rem', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.2)'}} onClick={() => deleteHistoryTask(task.id)}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {historyTasks.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{textAlign: 'center', padding: '3rem', color: 'var(--text-dim)'}}>暂无历史任务记录</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {showHistoryLogs && (
            <div style={{
              position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
              backgroundColor: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
              backdropFilter: 'blur(8px)'
            }}>
              <div className="card" style={{width: '90%', maxWidth: '1000px', maxHeight: '90vh', display: 'flex', flexDirection: 'column'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem'}}>
                  <h3>历史日志回溯</h3>
                  <button className="btn btn-outline" onClick={() => setShowHistoryLogs(false)}>关闭</button>
                </div>
                <div className="console" style={{flex: 1, height: 'auto', overflowY: 'auto'}}>
                  {historyLogs.map((log, i) => {
                    let logClass = "log-info";
                    if (log.includes("❌") || log.includes("🛑") || log.includes("错误")) logClass = "log-error";
                    else if (log.includes("✅") || log.includes("执行完毕")) logClass = "log-success";
                    return <div key={i} className={logClass}>{log}</div>;
                  })}
                </div>
              </div>
            </div>
          )}
          </div>
        )}
      </>
    )}
  </div>

  <div className="toast-container">
    {toasts.map(t => (
      <div key={t.id} className={`toast toast-${t.type}`}>
        {t.type === 'success' && <CheckCircle size={20} />}
        {t.type === 'error' && <XCircle size={20} />}
        {t.type === 'warning' && <AlertCircle size={20} />}
        {t.type === 'info' && <Info size={20} />}
        <div className="toast-message">{t.message}</div>
      </div>
    ))}
  </div>
  </>
  );
  }
  export default App;

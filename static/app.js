/* ==========================================================================
   智慧问答系统 · 前端交互脚本
   - 会话管理 / 历史记录 / 流式问答（WebSocket）
   - 主题切换、轻提示、Markdown 渲染（marked，带纯文本降级）
   ========================================================================== */

// ========== 调试开关：生产环境设为 false ==========
const DEBUG = false;

// 全局状态
let currentSessionId = null;
let isResponseInProgress = false;
let isDarkMode = true;

// DOM 元素
const chatHistory = document.getElementById('chatHistory'); // 聊天历史容器
const chatInput = document.getElementById('chatInput'); // 输入框
const sendBtn = document.getElementById('sendBtn'); // 发送按钮
const sourceFilter = document.getElementById('sourceFilter'); // 技术方向过滤器
const historyList = document.getElementById('historyList'); // 历史列表
const sessionInfo = document.getElementById('sessionInfo'); // 会话信息
const newSessionBtn = document.getElementById('newSessionBtn'); // 新会话按钮
const clearHistoryBtn = document.getElementById('clearHistoryBtn'); // 清除历史按钮
const loadingOverlay = document.getElementById('loadingOverlay'); // 加载遮罩
const themeToggle = document.getElementById('themeToggle'); // 主题切换按钮
const searchBox = document.getElementById('searchBox'); // 搜索框
const quickReplies = document.getElementById('quickReplies'); // 快捷回复
const quickReplyBtns = quickReplies.querySelectorAll('.quick-reply-btn'); // 快捷回复按钮
const emojiBtn = document.getElementById('emojiBtn'); // 表情按钮
const imageBtn = document.getElementById('imageBtn'); // 图片按钮
const fileBtn = document.getElementById('fileBtn'); // 文件按钮

// API URL 前缀，根据部署环境调整
const API_BASE_URL = ''; // 如果 API 和前端在同一域，可以留空

// 安全存取 localStorage：隐私模式 / 配额受限时可能抛异常，不能让它中断初始化
const storage = {
    get(key, fallback) {
        try {
            const value = localStorage.getItem(key);
            return value === null ? fallback : value;
        } catch (e) {
            return fallback;
        }
    },
    set(key, value) {
        try {
            localStorage.setItem(key, String(value));
        } catch (e) {
            /* 忽略：无法持久化时仅本次会话生效 */
        }
    }
};

// HTML 转义：用于纯文本降级渲染（Markdown 链路走 sanitizeHtml 清洗）
function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// 轻提示图标映射
const TOAST_ICONS = {
    success: 'fa-circle-check',
    error: 'fa-circle-exclamation',
    warning: 'fa-triangle-exclamation',
    info: 'fa-circle-info'
};

// 消息头像（机器人 / 用户）
const AVATAR_HTML = {
    user: '<i class="fas fa-user"></i>',
    system: '<i class="fas fa-robot"></i>'
};

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', async () => {
    if (DEBUG) console.log('%c✅ 智能问答系统前端已加载', 'color: #00ff00; font-weight: bold;');

    // 检查本地存储中的主题设置（默认深色）
    isDarkMode = storage.get('darkMode', 'true') !== 'false';
    updateTheme();

    // 先加载历史会话列表
    await loadHistory();

    // 然后创建新会话（会添加到列表顶部）
    await createNewSession();

    // 加载技术方向
    await loadSources();

    // 事件监听器
    sendBtn.addEventListener('click', sendMessage); // 发送按钮点击事件
    chatInput.addEventListener('keydown', (e) => { // 输入框键盘事件
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    newSessionBtn.addEventListener('click', createNewSession); // 新会话按钮点击事件
    clearHistoryBtn.addEventListener('click', clearHistory); // 清除历史按钮点击事件
    themeToggle.addEventListener('click', toggleTheme); // 主题切换按钮点击事件
    searchBox.addEventListener('input', searchHistory); // 搜索框输入事件

    // 快捷回复按钮点击事件
    quickReplyBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            chatInput.value = btn.textContent;
            chatInput.style.height = 'auto';
            chatInput.style.height = chatInput.scrollHeight + 'px';
            sendMessage();
        });
    });

    // 工具按钮点击事件（提供友好提示）
    emojiBtn.addEventListener('click', () => {
        showNotification('表情功能开发中，敬请期待！', 'info');
    });
    imageBtn.addEventListener('click', () => {
        showNotification('图片上传功能开发中，敬请期待！', 'info');
    });
    fileBtn.addEventListener('click', () => {
        showNotification('文件上传功能开发中，敬请期待！', 'info');
    });
});

// 切换主题
function toggleTheme() {
    isDarkMode = !isDarkMode;
    storage.set('darkMode', isDarkMode);
    updateTheme();
}

// 更新主题（主题类挂在 <html> 上，避免首屏闪烁）
function updateTheme() {
    document.documentElement.classList.toggle('dark-mode', isDarkMode);
    themeToggle.innerHTML = isDarkMode
        ? '<i class="fas fa-sun"></i>'
        : '<i class="fas fa-moon"></i>';
    themeToggle.setAttribute('aria-label', isDarkMode ? '切换到浅色主题' : '切换到深色主题');
    themeToggle.setAttribute('title', isDarkMode ? '切换到浅色主题' : '切换到深色主题');

    // 同步移动端浏览器地址栏颜色
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) {
        themeMeta.setAttribute('content', isDarkMode ? '#060b17' : '#eef3fb');
    }
}

// 搜索历史会话
function searchHistory() {
    const searchTerm = searchBox.value.toLowerCase();
    const historyItems = historyList.querySelectorAll('.history-item');

    historyItems.forEach(item => {
        const question = item.querySelector('.history-question');
        const answer = item.querySelector('.history-answer');
        const questionText = question ? question.textContent.toLowerCase() : '';
        const answerText = answer ? answer.textContent.toLowerCase() : '';

        if (questionText.includes(searchTerm) || answerText.includes(searchTerm)) {
            item.style.display = '';
        } else {
            item.style.display = 'none';
        }
    });
}

// 创建新会话
async function createNewSession() {
    showLoading();
    try {
        const response = await fetch(`${API_BASE_URL}/api/create_session`, {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('创建会话失败');
        }

        const data = await response.json();
        currentSessionId = data.session_id; // 更新当前会话 ID

        // 更新会话信息
        sessionInfo.textContent = `会话ID: ${currentSessionId.slice(0, 8)}...`;

        // 清空聊天历史并显示欢迎消息
        clearChatHistory();
        showWelcomeMessage();

        // 在历史列表中立即添加新会话项（显示0轮对话）
        addNewSessionToList(currentSessionId, 0);

    } catch (error) {
        console.error('创建会话错误:', error);
        showNotification('创建会话失败，请刷新页面重试', 'error');
    } finally {
        hideLoading();
    }
}

// ========== 共享：加载指定会话的历史到聊天区 ==========
async function loadSessionHistory(sessionId) {
    // 流式回答过程中切换会话会把正在写入的节点摘掉，直接拒绝
    if (isResponseInProgress) {
        showNotification('请等待当前回答完成后再切换会话', 'warning');
        return;
    }

    currentSessionId = sessionId;
    sessionInfo.textContent = `会话ID: ${sessionId.slice(0, 8)}...`;
    showLoading();
    try {
        const timestamp = new Date().getTime();
        const historyResponse = await fetch(`${API_BASE_URL}/api/history/${sessionId}?t=${timestamp}`, {
            cache: 'no-store'
        });
        if (!historyResponse.ok) throw new Error('获取历史记录失败');

        const historyData = await historyResponse.json();
        clearChatHistory();

        if (historyData.history && historyData.history.length > 0) {
            historyData.history.forEach(item => {
                addMessage('user', item.question);
                addMessage('system', item.answer);
            });
            showNotification(`已加载 ${historyData.history.length} 轮历史对话`, 'success');
        } else {
            addMessage('system', '暂无历史对话记录');
        }
        scrollToBottom();
    } catch (error) {
        console.error('加载历史会话失败:', error);
        showNotification('加载历史会话失败', 'error');
    } finally {
        hideLoading();
    }
}

// 在历史列表中添加新会话项
function addNewSessionToList(sessionId, count) {
    // 移除“暂无历史会话”占位，避免与新会话并列显示
    const emptyTip = historyList.querySelector('.history-empty');
    if (emptyTip) emptyTip.remove();

    const sessionItem = document.createElement('div');
    sessionItem.className = 'history-item';

    const questionElement = document.createElement('div');
    questionElement.className = 'history-question';
    questionElement.textContent = `会话 ${sessionId.slice(0, 8)}...`;

    const answerElement = document.createElement('div');
    answerElement.className = 'history-answer';
    answerElement.textContent = `共 ${count} 轮对话`;

    sessionItem.appendChild(questionElement);
    sessionItem.appendChild(answerElement);
    sessionItem.addEventListener('click', () => loadSessionHistory(sessionId));

    if (historyList.firstChild) {
        historyList.insertBefore(sessionItem, historyList.firstChild);
    } else {
        historyList.appendChild(sessionItem);
    }
}

// 加载技术方向
async function loadSources() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/sources`);

        if (!response.ok) {
            throw new Error('获取技术方向失败');
        }

        const data = await response.json();

        // 清空现有选项
        sourceFilter.innerHTML = '<option value="">全部</option>';

        // 添加技术方向选项
        data.sources.forEach(source => {
            const option = document.createElement('option');
            option.value = source;
            option.textContent = source;
            sourceFilter.appendChild(option);
        });

    } catch (error) {
        console.error('加载技术方向错误:', error);
    }
}

// 加载历史消息（支持多轮 QA）
async function loadHistory() {
    try {
        // 添加时间戳参数，防止浏览器缓存
        const timestamp = new Date().getTime();
        const response = await fetch(`${API_BASE_URL}/api/sessions?t=${timestamp}`, {
            cache: 'no-store'  // 明确禁用缓存
        });

        if (!response.ok) {
            throw new Error('获取会话列表失败');
        }

        const data = await response.json();

        // 清空历史列表
        historyList.innerHTML = '';

        // 如果没有会话，显示提示
        if (data.sessions.length === 0) {
            const emptyItem = document.createElement('div');
            emptyItem.className = 'history-item history-empty';
            emptyItem.innerHTML = `
                <div class="history-question">暂无历史会话</div>
                <div class="history-answer">开始新的对话吧！</div>
            `;
            historyList.appendChild(emptyItem);
            return;
        }

        // 显示所有会话（全部用 textContent 写入，避免 HTML 注入）
        data.sessions.forEach(session => {
            const sessionItem = document.createElement('div');
            sessionItem.className = 'history-item';

            const previewText = session.last_question || `会话 ${session.session_id.slice(0, 8)}...`;
            const questionElement = document.createElement('div');
            questionElement.className = 'history-question';
            questionElement.textContent = previewText;
            questionElement.title = previewText;

            const answerElement = document.createElement('div');
            answerElement.className = 'history-answer';
            answerElement.textContent = `共 ${session.count} 轮对话 · ${session.last_time || ''}`;

            sessionItem.appendChild(questionElement);
            sessionItem.appendChild(answerElement);
            sessionItem.addEventListener('click', () => loadSessionHistory(session.session_id));
            historyList.appendChild(sessionItem);
        });

    } catch (error) {
        console.error('加载历史记录错误:', error);
    }
}

// 清除所有历史记录
async function clearHistory() {
    if (!currentSessionId) return;

    if (!confirm('确定要清除所有历史记录吗？')) {
        return;
    }

    showLoading();
    try {
        const response = await fetch(`${API_BASE_URL}/api/history`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('清除历史记录失败');
        }

        // 清空历史列表
        historyList.innerHTML = '';

        // 清空聊天历史并显示提示
        clearChatHistory();
        addMessage('system', '所有历史记录已清除，有什么我可以帮您的吗？');

        // 重新加载历史记录列表
        await loadHistory();

    } catch (error) {
        console.error('清除历史记录错误:', error);
        showNotification('清除历史记录失败', 'error');
    } finally {
        hideLoading();
    }
}

// 清空聊天历史（真正清空，不添加任何消息）
function clearChatHistory() {
    chatHistory.innerHTML = '';
}

// 显示欢迎消息
function showWelcomeMessage() {
    const messageElement = document.createElement('div');
    messageElement.className = 'message system-message';
    messageElement.innerHTML = `
        <div class="message-header">
            <div class="avatar">${AVATAR_HTML.system}</div>
            <span>智能助手</span>
        </div>
        <div class="message-content">
            您好！我是智能问答助手，有什么我可以帮您的吗？
        </div>
    `;
    chatHistory.appendChild(messageElement);
}

// 显示加载遮罩
function showLoading() {
    loadingOverlay.classList.add('is-visible');
    loadingOverlay.setAttribute('aria-busy', 'true');
}

// 隐藏加载遮罩
function hideLoading() {
    loadingOverlay.classList.remove('is-visible');
    loadingOverlay.setAttribute('aria-busy', 'false');
}

// 发送消息
async function sendMessage() {
    const query = chatInput.value.trim();
    const filter = sourceFilter.value;

    if (!query || isResponseInProgress) return;

    // 会话尚未建立（如启动时创建失败）先补建，避免带着 null 的 session_id 发请求
    if (!currentSessionId) {
        await createNewSession();
        if (!currentSessionId) {
            showNotification('会话未就绪，请刷新页面重试', 'error');
            return;
        }
    }

    // 重置输入框
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // 添加用户消息到聊天窗口
    addMessage('user', query);

    // 设置正在响应标志
    isResponseInProgress = true;
    sendBtn.disabled = true;
    newSessionBtn.disabled = true;
    clearHistoryBtn.disabled = true;
    quickReplyBtns.forEach(btn => { btn.disabled = true; });
    if (DEBUG) console.log('发送:', query.substring(0, 50));

    // 添加正在输入指示器
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.innerHTML = '<span></span><span></span><span></span>';
    chatHistory.appendChild(typingIndicator);
    scrollToBottom();

    try {
        // 创建系统消息容器（首个 token 到达前先隐藏，避免出现只有一个头像的空框）
        const messageElement = document.createElement('div');
        messageElement.className = 'message system-message is-pending';
        messageElement.innerHTML = `
            <div class="message-header">
                <div class="avatar">${AVATAR_HTML.system}</div>
                <span>智能助手</span>
            </div>
            <div class="message-content"></div>
        `;
        const contentElement = messageElement.querySelector('.message-content');
        chatHistory.appendChild(messageElement);

        // 建立 WebSocket 连接进行流式输出
        await handleStreamingResponse(query, filter, contentElement, typingIndicator);

        // 等待后端保存后刷新侧边栏
        await new Promise(resolve => setTimeout(resolve, 500));
        await loadHistory();

    } catch (error) {
        console.error('发送消息错误:', error);
        if (typingIndicator && typingIndicator.parentNode) {
            chatHistory.removeChild(typingIndicator);
        }
        // 未收到任何内容的空气泡一并清掉，错误只提示一次
        chatHistory.querySelectorAll('.message.is-pending').forEach(el => el.remove());
        const reason = (error && error.message) ? error.message : '网络连接异常';
        addMessage('system', `抱歉，发生错误: ${reason}`);
    } finally {
        isResponseInProgress = false;
        sendBtn.disabled = false;
        newSessionBtn.disabled = false;
        clearHistoryBtn.disabled = false;
        quickReplyBtns.forEach(btn => { btn.disabled = false; });
        scrollToBottom();
    }
}

// 处理流式响应
async function handleStreamingResponse(query, filter, contentElement, typingIndicator) {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}${API_BASE_URL}/api/stream`;

    return new Promise((resolve, reject) => {
        const currentSocket = new WebSocket(wsUrl);
        let accumulatedContent = '';
        let isCompleted = false;
        let resolveCalled = false;
        let rafPending = false; // rAF 节流标记
        let idleTimer = null; // 空闲超时：建连、每次收到消息都会重置

        // 首个 token 到达时再显示消息框
        const messageHost = contentElement.parentElement;
        const reveal = () => {
            if (messageHost) messageHost.classList.remove('is-pending');
        };

        const finish = (err) => {
            if (resolveCalled) return;
            resolveCalled = true;
            isCompleted = true;
            clearTimeout(idleTimer);
            // 正常收尾时确保消息可见（异常路径由 sendMessage 的 catch 统一清理）
            if (!err) reveal();
            // 防御：没有 start 消息就结束时，别把跳动点留在界面上
            if (typingIndicator && typingIndicator.parentNode) {
                typingIndicator.remove();
            }
            currentSocket.close();
            if (err) reject(err); else resolve();
        };

        // 建连与流式输出都可能卡住，超时必须覆盖整个过程，而不只是握手阶段
        const armIdleTimeout = () => {
            clearTimeout(idleTimer);
            idleTimer = setTimeout(() => {
                if (!isCompleted) finish(new Error('响应超时，请稍后重试'));
            }, 90000);
        };

        armIdleTimeout();

        currentSocket.onopen = function() {
            armIdleTimeout();
            currentSocket.send(JSON.stringify({
                query: query,
                source_filter: filter,
                session_id: currentSessionId
            }));
        };

        currentSocket.onmessage = function(event) {
            armIdleTimeout();
            try {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'start':
                        if (typingIndicator && typingIndicator.parentNode) {
                            typingIndicator.parentNode.removeChild(typingIndicator);
                        }
                        break;

                    case 'token':
                        // 后端可能发出空 token（如 FAQ 未命中），空内容不算“已收到回答”
                        if (data.token) {
                            accumulatedContent += data.token;
                            // 用 rAF 节流 DOM 更新，避免每个 token 都触发重排
                            if (!rafPending) {
                                rafPending = true;
                                requestAnimationFrame(() => {
                                    reveal();
                                    contentElement.innerHTML = safeParseMarkdown(accumulatedContent);
                                    scrollToBottom(false);
                                    rafPending = false;
                                });
                            }
                        }
                        break;

                    case 'end':
                        isCompleted = true;
                        reveal();
                        contentElement.innerHTML = safeParseMarkdown(
                            accumulatedContent.trim() ? accumulatedContent : '未找到相关答案，请尝试其他问题。'
                        );
                        finish(null);
                        break;

                    case 'error':
                        // 不在这里写错误文案，交给 sendMessage 的 catch 统一提示，避免重复
                        isCompleted = true;
                        finish(new Error(data.error));
                        break;
                }
            } catch (parseError) {
                console.error('解析消息失败:', parseError);
            }
        };

        currentSocket.onerror = function() {
            // 事件对象没有可读的 message，统一给一句人话，文案由 catch 输出
            if (!isCompleted) {
                finish(new Error('网络连接异常，请检查网络后重试'));
            }
        };

        currentSocket.onclose = function(event) {
            if (resolveCalled) return;
            if (accumulatedContent.trim()) {
                // 已收到内容：非正常关闭（如 1006）时回答可能不完整，提示一下但保留内容
                if (event.code !== 1000) {
                    showNotification('连接提前断开，回答可能不完整', 'warning');
                }
                finish(null);
            } else if (event.code === 1000) {
                // 正常关闭却没有任何内容：不留隐藏气泡，明确告诉用户
                finish(new Error('连接已关闭，没有收到回答'));
            } else {
                finish(new Error('连接异常关闭'));
            }
        };
    });
}

// 清洗渲染后的 HTML：移除脚本类标签、内联事件与危险协议（marked 默认放行原始 HTML）
function sanitizeHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = html;

    // 1) 直接移除可执行 / 可嵌套页面的标签
    template.content
        .querySelectorAll('script, style, iframe, frame, frameset, object, embed, link, meta, base, template, form, input, textarea, button, svg, math')
        .forEach(node => node.remove());

    // 2) 逐元素清理属性：事件处理器、内联样式一律去掉
    const URL_ATTRS = ['href', 'src', 'xlink:href', 'action', 'formaction', 'poster', 'background'];
    const SAFE_SCHEME = /^(https?:|mailto:|tel:)/;

    template.content.querySelectorAll('*').forEach(node => {
        Array.from(node.attributes).forEach(attr => {
            const name = attr.name.toLowerCase();

            if (name.startsWith('on') || name === 'style' || name === 'srcdoc') {
                node.removeAttribute(attr.name);
                return;
            }

            // 去掉可用于伪装界面的 id/name/class，以及能带出 URL 列表的属性
            if (name === 'id' || name === 'name' || name === 'class' ||
                name === 'srcset' || name === 'imagesrcset' || name === 'ping') {
                node.removeAttribute(attr.name);
                return;
            }

            if (!URL_ATTRS.includes(name)) return;

            // 浏览器解析 URL 时会忽略 scheme 内部的空白与控制字符，比较前先做同样处理，
            // 避免 "java\tscript:" 这类绕过
            const value = attr.value.replace(/[\u0000-\u0020\u007f-\u009f]/g, '').toLowerCase();
            const hasScheme = /^[a-z][a-z0-9+.-]*:/.test(value);

            if (hasScheme && !SAFE_SCHEME.test(value)) {
                node.removeAttribute(attr.name);
            }
        });
    });

    return template.innerHTML;
}

// 安全解析 Markdown：
// 1) 交给 marked 解析 Markdown 语法（marked 默认会放行原始 HTML）
// 2) 渲染结果再经过 sanitizeHtml 白名单清洗，脚本 / 事件属性 / javascript: 链接都会被剔除
// 3) marked 不可用（如 CDN 被拦截）时退化为纯文本 + 换行
function safeParseMarkdown(text) {
    if (!text && text !== 0) return '';
    const str = String(text);
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        try {
            return sanitizeHtml(marked.parse(str));
        } catch (e) {
            console.warn('marked.parse 解析失败，使用纯文本回退:', e.message);
        }
    }
    return escapeHtml(str).replace(/\n/g, '<br>');
}

// 添加消息到聊天窗口（支持 Markdown 格式）
function addMessage(type, content) {
    // 防御：内容为空时记录警告
    if (!content && content !== 0) {
        console.warn(`⚠️ addMessage(${type}): 内容为空`, { type, content });
    }

    const messageElement = document.createElement('div');
    messageElement.className = `message ${type === 'user' ? 'user-message' : 'system-message'}`;

    // 添加消息头部
    const headerElement = document.createElement('div');
    headerElement.className = 'message-header';

    if (type === 'user') {
        headerElement.innerHTML = `
            <div class="avatar">${AVATAR_HTML.user}</div>
            <span>我</span>
        `;
    } else {
        headerElement.innerHTML = `
            <div class="avatar">${AVATAR_HTML.system}</div>
            <span>智能助手</span>
        `;
    }

    const contentElement = document.createElement('div');
    contentElement.className = 'message-content';
    // 使用安全解析函数（支持降级到纯文本）
    contentElement.innerHTML = safeParseMarkdown(content);

    messageElement.appendChild(headerElement);
    messageElement.appendChild(contentElement);
    chatHistory.appendChild(messageElement);

    // 滚动到底部
    scrollToBottom();
}

// 智能滚动：默认强制滚到底部；force=false 时仅在用户处于底部附近才自动滚
function scrollToBottom(force = true) {
    if (force) {
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }
    // 用户距离底部 60px 以内才自动滚动，否则用户可能在查看上方内容
    const threshold = 60;
    const distanceFromBottom = chatHistory.scrollHeight - chatHistory.scrollTop - chatHistory.clientHeight;
    if (distanceFromBottom < threshold) {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
}

// 当前屏幕上的轻提示（用于纵向堆叠，避免互相遮挡）
const activeToasts = [];

// 重新排列轻提示的位置
function layoutToasts() {
    activeToasts.forEach((toast, index) => {
        toast.style.top = `${84 + index * 76}px`;
    });
}

// 显示通知消息
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `toast toast-${type}`;
    notification.setAttribute('role', 'status');

    const icon = document.createElement('i');
    icon.className = `fas ${TOAST_ICONS[type] || TOAST_ICONS.info}`;
    icon.setAttribute('aria-hidden', 'true');

    const text = document.createElement('span');
    text.textContent = message;

    notification.appendChild(icon);
    notification.appendChild(text);
    document.body.appendChild(notification);

    // 最多同时显示 3 条，超出时挤掉最早的一条
    activeToasts.push(notification);
    while (activeToasts.length > 3) {
        const oldest = activeToasts.shift();
        if (oldest && oldest.parentNode) oldest.remove();
    }
    layoutToasts();

    // 下一帧再触发过渡动画
    requestAnimationFrame(() => notification.classList.add('is-visible'));

    // 3 秒后自动移除
    setTimeout(() => {
        notification.classList.remove('is-visible');
        setTimeout(() => {
            const index = activeToasts.indexOf(notification);
            if (index > -1) activeToasts.splice(index, 1);
            if (notification.parentNode) notification.remove();
            layoutToasts();
        }, 320);
    }, 3000);
}

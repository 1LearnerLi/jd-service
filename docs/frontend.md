# 电商智能客服系统 — 前端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Vue 3 + Vite + TypeScript + Element Plus 的智能客服前端，包含登录页和聊天主界面（会话列表 + 消息区 + SSE 流式展示）。

**Architecture:** 单页应用（SPA），Vue Router 管理路由，Pinia 管理状态，fetch + EventSource 处理后端通信（REST + SSE）。组件树：LoginView → ChatView(SessionSidebar + ChatMain(MessageList + ChatInput))。

**Tech Stack:** Vue 3.4+, Vite 6+, TypeScript 5.7+, Element Plus 2.x, Pinia 2.x, Vue Router 4.x

## Global Constraints

- 变量/文件名使用英文
- 组件使用 Composition API (`<script setup lang="ts">`)
- 样式使用 scoped SCSS
- 所有 API 调用通过统一客户端封装
- 目标覆盖率 80%+

---

### Task 1: 前端项目初始化

**Files:**
- Create: `frontend/` (整个目录)

**Interfaces:**
- Produces: `npm run dev` 可启动开发服务器

- [ ] **Step 1: 使用 Vite 创建 Vue 3 + TypeScript 项目**

```bash
npm create vite@latest frontend -- --template vue-ts
```

- [ ] **Step 2: 安装依赖**

```bash
cd frontend
npm install
npm install element-plus pinia vue-router@4
npm install -D sass @types/node
```

- [ ] **Step 3: 配置 vite.config.ts**

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: 配置 tsconfig.json 路径别名**

在 `tsconfig.app.json` 的 `compilerOptions` 中添加：
```json
"baseUrl": ".",
"paths": {
  "@/*": ["src/*"]
}
```

- [ ] **Step 5: 在 main.ts 中引入 Element Plus**

```typescript
// frontend/src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
```

- [ ] **Step 6: 验证项目可启动**

```bash
cd frontend && npm run dev
```

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "chore: 初始化前端项目（Vue 3 + Vite + TypeScript + Element Plus）"
```

---

### Task 2: TypeScript 类型定义

**Files:**
- Create: `frontend/src/types/index.ts`

**Interfaces:**
- Produces:
  - `Session{ id, userId, title, status, createdAt, updatedAt }`
  - `Message{ id, sessionId, role, content, intent, slotsJson, createdAt }`
  - `APIResponse<T>{ success, data, error, meta }`

- [ ] **Step 1: 创建 frontend/src/types/index.ts**

```typescript
/** 会话 */
export interface Session {
  id: string
  user_id: string
  title: string | null
  status: 'active' | 'closed'
  created_at: string
  updated_at: string
}

/** 消息 */
export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  intent: string | null
  slots_json: Record<string, unknown> | null
  created_at: string
}

/** 会话详情（含消息列表） */
export interface SessionDetail {
  session: Session
  messages: Message[]
}

/** 统一 API 响应信封 */
export interface APIResponse<T = unknown> {
  success: boolean
  data: T | null
  error: string | null
  meta: Record<string, unknown> | null
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/
git commit -m "feat: 添加前端 TypeScript 类型定义"
```

---

### Task 3: API 客户端封装

**Files:**
- Create: `frontend/src/api/client.ts`

**Interfaces:**
- Produces:
  - `createSession(userId: string): Promise<Session>`
  - `fetchSessions(userId: string): Promise<Session[]>`
  - `fetchSession(sessionId: string): Promise<SessionDetail>`
  - `sendMessage(sessionId: string, content: string, onToken: (token: string) => void, onDone: () => void): Promise<void>`

- [ ] **Step 1: 创建 frontend/src/api/client.ts**

```typescript
import type { APIResponse, Session, SessionDetail } from '@/types'

const BASE_URL = '/api/v1'

/** 通用 fetch 封装 */
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${response.status}`)
  }

  const json: APIResponse<T> = await response.json()
  if (!json.success) {
    throw new Error(json.error || '请求失败')
  }

  return json.data as T
}

/** 创建会话 */
export async function createSession(userId: string): Promise<Session> {
  return request<Session>(`/sessions?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
  })
}

/** 获取会话列表 */
export async function fetchSessions(userId: string): Promise<Session[]> {
  return request<Session[]>(`/sessions?user_id=${encodeURIComponent(userId)}`)
}

/** 获取会话详情及消息 */
export async function fetchSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/sessions/${encodeURIComponent(sessionId)}`)
}

/** 发送消息，通过 SSE 流式接收回复 */
export async function sendMessage(
  sessionId: string,
  content: string,
  onToken: (token: string) => void,
  onDone: () => void,
): Promise<void> {
  const url = `${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/messages?content=${encodeURIComponent(content)}`

  const response = await fetch(url, { method: 'POST' })

  if (!response.ok) {
    throw new Error(`发送消息失败: HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('浏览器不支持流式读取')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data:')) {
        const data = line.slice(5).trim()
        if (data) {
          onToken(data)
        }
      }
      if (line.startsWith('event: done')) {
        onDone()
        return
      }
    }
  }

  onDone()
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: 添加前端 API 客户端和 SSE 流式支持"
```

---

### Task 4: 路由配置

**Files:**
- Create: `frontend/src/router/index.ts`

**Interfaces:**
- Produces:
  - `/login` → `LoginView`
  - `/chat` → `ChatView`
  - `/` 重定向到 `/login`

- [ ] **Step 1: 创建 frontend/src/router/index.ts**

```typescript
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/login',
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('@/views/ChatView.vue'),
    },
  ],
})

export default router
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/
git commit -m "feat: 添加前端路由配置"
```

---

### Task 5: Pinia 状态管理 — SessionStore

**Files:**
- Create: `frontend/src/stores/session.ts`

**Interfaces:**
- Produces:
  - `useSessionStore`: userId, sessions, activeSessionId
  - `setUserId(id)`, `createSession()`, `setActiveSession(id)`

- [ ] **Step 1: 创建 frontend/src/stores/session.ts**

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Session } from '@/types'
import { createSession, fetchSessions } from '@/api/client'

export const useSessionStore = defineStore('session', () => {
  const userId = ref('')
  const sessions = ref<Session[]>([])
  const activeSessionId = ref<string | null>(null)

  /** 设置当前用户 ID */
  function setUserId(id: string) {
    userId.value = id
  }

  /** 加载会话列表 */
  async function loadSessions() {
    if (!userId.value) return
    sessions.value = await fetchSessions(userId.value)
  }

  /** 创建新会话 */
  async function createNewSession() {
    if (!userId.value) return
    const session = await createSession(userId.value)
    sessions.value.unshift(session)
    activeSessionId.value = session.id
    return session
  }

  /** 设置当前活跃会话 */
  function setActiveSession(id: string) {
    activeSessionId.value = id
  }

  return {
    userId,
    sessions,
    activeSessionId,
    setUserId,
    loadSessions,
    createNewSession,
    setActiveSession,
  }
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/session.ts
git commit -m "feat: 添加会话 Pinia Store"
```

---

### Task 6: Pinia 状态管理 — ChatStore

**Files:**
- Create: `frontend/src/stores/chat.ts`

**Interfaces:**
- Produces:
  - `useChatStore`: messages, isStreaming, streamingContent
  - `fetchMessages(sessionId)`, `sendMessage(content)`, `clearMessages()`

- [ ] **Step 1: 创建 frontend/src/stores/chat.ts**

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Message } from '@/types'
import { fetchSession, sendMessage as apiSendMessage } from '@/api/client'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const currentSessionId = ref<string | null>(null)

  /** 获取会话消息列表 */
  async function loadMessages(sessionId: string) {
    currentSessionId.value = sessionId
    const detail = await fetchSession(sessionId)
    messages.value = detail.messages
  }

  /** 发送消息 */
  async function sendMessage(content: string) {
    if (!currentSessionId.value || isStreaming.value) return

    // 添加用户消息到列表
    const userMsg: Message = {
      id: Date.now(),
      role: 'user',
      content,
      intent: null,
      slots_json: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg)

    // 开始流式回复
    isStreaming.value = true
    streamingContent.value = ''

    try {
      await apiSendMessage(
        currentSessionId.value,
        content,
        (token) => {
          streamingContent.value += token
        },
        () => {
          // 流式结束，将内容作为完整消息添加
          if (streamingContent.value) {
            const assistantMsg: Message = {
              id: Date.now(),
              role: 'assistant',
              content: streamingContent.value,
              intent: null,
              slots_json: null,
              created_at: new Date().toISOString(),
            }
            messages.value.push(assistantMsg)
          }
          streamingContent.value = ''
          isStreaming.value = false
        },
      )
    } catch (err) {
      console.error('发送消息失败:', err)
      isStreaming.value = false
      streamingContent.value = ''
    }
  }

  /** 清空消息 */
  function clearMessages() {
    messages.value = []
    currentSessionId.value = null
  }

  return {
    messages,
    isStreaming,
    streamingContent,
    loadMessages,
    sendMessage,
    clearMessages,
  }
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/chat.ts
git commit -m "feat: 添加聊天 Pinia Store"
```

---

### Task 7: LoginView 组件

**Files:**
- Create: `frontend/src/views/LoginView.vue`

**Interfaces:**
- Produces: 登录页面，输入 user_id（默认 1001），点击确定后跳转 `/chat`

- [ ] **Step 1: 创建 frontend/src/views/LoginView.vue**

```vue
<template>
  <div class="login-container">
    <div class="login-card">
      <h1 class="login-title">🛒 电商智能客服</h1>
      <p class="login-subtitle">请输入您的用户 ID 以开始对话</p>

      <el-form @submit.prevent="handleLogin" class="login-form">
        <el-form-item>
          <el-input
            v-model="userId"
            placeholder="请输入用户 ID"
            size="large"
            clearable
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="isLoading"
            @click="handleLogin"
            class="login-button"
          >
            进入客服
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const sessionStore = useSessionStore()

const userId = ref('1001')
const isLoading = ref(false)

async function handleLogin() {
  if (!userId.value.trim()) return

  isLoading.value = true
  try {
    sessionStore.setUserId(userId.value.trim())
    // 进入聊天页面前先加载会话列表
    await sessionStore.loadSessions()
    router.push('/chat')
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped lang="scss">
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 420px;
  padding: 48px 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  text-align: center;
  margin-bottom: 8px;
  color: #303133;
}

.login-subtitle {
  text-align: center;
  color: #909399;
  margin-bottom: 32px;
  font-size: 14px;
}

.login-form {
  width: 100%;
}

.login-button {
  width: 100%;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/LoginView.vue
git commit -m "feat: 添加登录页面组件"
```

---

### Task 8: SessionSidebar 组件

**Files:**
- Create: `frontend/src/components/SessionSidebar.vue`

**Interfaces:**
- Consumes: `useSessionStore`
- Produces: 左侧会话列表侧边栏（280px 宽），含新建会话按钮和会话列表

- [ ] **Step 1: 创建 frontend/src/components/SessionSidebar.vue**

```vue
<template>
  <aside class="session-sidebar">
    <div class="sidebar-header">
      <el-button
        type="primary"
        class="new-session-btn"
        @click="handleCreateSession"
      >
        <el-icon><Plus /></el-icon>
        创建新会话
      </el-button>
    </div>

    <div class="session-list">
      <div
        v-for="session in sessionStore.sessions"
        :key="session.id"
        :class="['session-item', { active: session.id === sessionStore.activeSessionId }]"
        @click="handleSelectSession(session.id)"
      >
        <div class="session-title">
          {{ session.title || '新会话' }}
        </div>
        <div class="session-time">
          {{ formatTime(session.updated_at) }}
        </div>
      </div>

      <el-empty
        v-if="sessionStore.sessions.length === 0"
        description="暂无会话"
        :image-size="60"
      />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

/** 创建新会话 */
async function handleCreateSession() {
  await sessionStore.createNewSession()
  if (sessionStore.activeSessionId) {
    await chatStore.loadMessages(sessionStore.activeSessionId)
  }
}

/** 选择会话 */
async function handleSelectSession(sessionId: string) {
  sessionStore.setActiveSession(sessionId)
  await chatStore.loadMessages(sessionId)
}

/** 格式化时间 */
function formatTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return date.toLocaleDateString('zh-CN')
}
</script>

<style scoped lang="scss">
.session-sidebar {
  width: 280px;
  min-width: 280px;
  height: 100vh;
  background: #f5f7fa;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.new-session-btn {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  padding: 12px 16px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;

  &:hover {
    background: #e8ecf1;
  }

  &.active {
    background: #d9e1f2;
  }
}

.session-title {
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.session-time {
  font-size: 12px;
  color: #909399;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SessionSidebar.vue
git commit -m "feat: 添加会话侧边栏组件"
```

---

### Task 9: MessageBubble 与 MessageList 组件

**Files:**
- Create: `frontend/src/components/MessageBubble.vue`
- Create: `frontend/src/components/MessageList.vue`

- [ ] **Step 1: 创建 frontend/src/components/MessageBubble.vue**

```vue
<template>
  <div :class="['message-bubble', role]">
    <div :class="['bubble-avatar', role]">
      {{ role === 'user' ? '👤' : '🤖' }}
    </div>
    <div :class="['bubble-content', role]">
      <div class="bubble-text">{{ content }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  role: 'user' | 'assistant'
  content: string
}>()
</script>

<style scoped lang="scss">
.message-bubble {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  padding: 0 16px;

  &.user {
    flex-direction: row-reverse;
  }
}

.bubble-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;

  &.user {
    background: #e8f4fd;
  }

  &.assistant {
    background: #f0f0f0;
  }
}

.bubble-content {
  max-width: 70%;
  padding: 10px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;

  &.user {
    background: #409eff;
    color: #fff;
    border-bottom-right-radius: 4px;
  }

  &.assistant {
    background: #f0f0f0;
    color: #303133;
    border-bottom-left-radius: 4px;
  }
}

.bubble-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
```

- [ ] **Step 2: 创建 frontend/src/components/MessageList.vue**

```vue
<template>
  <div class="message-list" ref="listRef">
    <div v-if="messages.length === 0 && !isStreaming" class="empty-hint">
      <el-empty description="发送消息开始对话" :image-size="80" />
    </div>

    <MessageBubble
      v-for="msg in messages"
      :key="msg.id"
      :role="msg.role"
      :content="msg.content"
    />

    <!-- 流式回复中 -->
    <MessageBubble
      v-if="isStreaming && streamingContent"
      role="assistant"
      :content="streamingContent + '▊'"
    />

    <div v-if="isStreaming && !streamingContent" class="typing-hint">
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
      <span class="typing-dot"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { Message } from '@/types'
import MessageBubble from './MessageBubble.vue'

const props = defineProps<{
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
}>()

const listRef = ref<HTMLDivElement>()

/** 自动滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

watch(
  () => [props.messages.length, props.streamingContent],
  () => scrollToBottom(),
  { deep: true },
)
</script>

<style scoped lang="scss">
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  background: #fff;
}

.empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.typing-hint {
  display: flex;
  gap: 6px;
  padding: 12px 32px;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: typing 1.4s infinite ease-in-out;

  &:nth-child(2) {
    animation-delay: 0.2s;
  }

  &:nth-child(3) {
    animation-delay: 0.4s;
  }
}

@keyframes typing {
  0%, 60%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  30% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MessageBubble.vue frontend/src/components/MessageList.vue
git commit -m "feat: 添加消息气泡和消息列表组件"
```

---

### Task 10: ChatInput 组件

**Files:**
- Create: `frontend/src/components/ChatInput.vue`

- [ ] **Step 1: 创建 frontend/src/components/ChatInput.vue**

```vue
<template>
  <div class="chat-input">
    <div class="input-wrapper">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        placeholder="输入消息，按 Enter 发送..."
        resize="none"
        :disabled="isStreaming"
        @keydown.enter.exact.prevent="handleSend"
      />
      <el-button
        type="primary"
        :disabled="!inputText.trim() || isStreaming"
        :loading="isStreaming"
        @click="handleSend"
        class="send-btn"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  isStreaming: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
}>()

const inputText = ref('')

function handleSend() {
  const content = inputText.value.trim()
  if (!content || props.isStreaming) return

  emit('send', content)
  inputText.value = ''
}
</script>

<style scoped lang="scss">
.chat-input {
  padding: 12px 16px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}

.input-wrapper {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.send-btn {
  height: 58px;
  min-width: 80px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatInput.vue
git commit -m "feat: 添加聊天输入框组件"
```

---

### Task 11: ChatMain 组件

**Files:**
- Create: `frontend/src/components/ChatMain.vue`

- [ ] **Step 1: 创建 frontend/src/components/ChatMain.vue**

```vue
<template>
  <div class="chat-main">
    <!-- 顶部会话标题 -->
    <div class="chat-header">
      <span class="chat-title">
        {{ sessionTitle }}
      </span>
    </div>

    <!-- 消息列表 -->
    <MessageList
      :messages="chatStore.messages"
      :is-streaming="chatStore.isStreaming"
      :streaming-content="chatStore.streamingContent"
    />

    <!-- 输入框 -->
    <ChatInput
      :is-streaming="chatStore.isStreaming"
      @send="handleSend"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import { useChatStore } from '@/stores/chat'
import MessageList from './MessageList.vue'
import ChatInput from './ChatInput.vue'

const sessionStore = useSessionStore()
const chatStore = useChatStore()

const sessionTitle = computed(() => {
  const active = sessionStore.sessions.find(
    (s) => s.id === sessionStore.activeSessionId,
  )
  return active?.title || '选择或创建一个会话开始聊天'
})

async function handleSend(content: string) {
  await chatStore.sendMessage(content)
}
</script>

<style scoped lang="scss">
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #fff;
}

.chat-header {
  padding: 14px 20px;
  border-bottom: 1px solid #e4e7ed;
  background: #fafafa;
}

.chat-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ChatMain.vue
git commit -m "feat: 添加聊天主区域组件"
```

---

### Task 12: ChatView 页面

**Files:**
- Create: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: 创建 frontend/src/views/ChatView.vue**

```vue
<template>
  <div class="chat-view">
    <SessionSidebar />
    <ChatMain />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import SessionSidebar from '@/components/SessionSidebar.vue'
import ChatMain from '@/components/ChatMain.vue'

const router = useRouter()
const sessionStore = useSessionStore()

onMounted(() => {
  // 如果未设置 userId，跳回登录页
  if (!sessionStore.userId) {
    router.replace('/login')
  }
})
</script>

<style scoped lang="scss">
.chat-view {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat: 添加聊天主页面"
```

---

### Task 13: App.vue 根组件

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 修改 frontend/src/App.vue**

```vue
<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
    'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
}

#app {
  width: 100%;
  height: 100vh;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: 配置 App 根组件"
```

---

### Task 14: 前端集成验证

**验证流程：**

- [ ] **Step 1: 确保后端已启动**

```bash
# 终端 1：启动 Docker MySQL
docker compose -f docker/docker-compose.yaml up -d mysql

# 终端 2：启动后端
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 2: 启动前端开发服务器**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 验证完整流程**

1. 浏览器打开 `http://localhost:5173`，应跳转到登录页
2. 输入 user_id（默认 1001），点击"进入客服"，应跳转到聊天页
3. 点击"创建新会话"，应创建成功并出现在左侧
4. 输入消息（如"你好"），发送，应看到用户消息和 AI 流式回复
5. 切换会话，消息列表应正确更新

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "chore: 前端集成验证通过"
```

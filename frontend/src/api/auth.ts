/** auth 模块 API 封装：对应 backend auth/api.py（登录由 stores/auth.ts 直接调 client）。 */
import { api } from './client'
import type { TokenIssueIn, TokenIssueOut, TokenOut } from './types'

export const tokensApi = {
  /** 我的令牌列表（已吊销的不出现；不含明文与哈希）。 */
  list: () => api.get<TokenOut[]>('/auth/tokens'),
  /** 签发令牌：响应里的明文只此一次，关掉就取不回。 */
  issue: (data: TokenIssueIn) => api.post<TokenIssueOut>('/auth/tokens', data),
  /** 吊销令牌（立刻失效，记录保留）。 */
  revoke: (id: number) => api.delete<void>(`/auth/tokens/${id}`),
}

import Taro from '@tarojs/taro'
import { ApiError } from './api'
import { requestIdFrom, SecureRandomUnavailable } from './request-id-core'

// This only prepares a platform request ID. It does not enable mini-program
// transport, model credentials, hosted authentication or any network access.
export async function createRequestId(): Promise<string> {
  try {
    return await requestIdFrom(async () => {
      if (process.env.TARO_ENV === 'h5') {
        if (typeof globalThis.crypto?.getRandomValues !== 'function') throw new SecureRandomUnavailable()
        return globalThis.crypto.getRandomValues(new Uint8Array(16))
      }
      if (process.env.TARO_ENV === 'weapp') {
        if (typeof Taro.getRandomValues !== 'function') throw new SecureRandomUnavailable()
        const result = await Taro.getRandomValues({ length: 16 })
        return result.randomValues
      }
      throw new SecureRandomUnavailable()
    })
  } catch {
    throw new ApiError('SECURE_RANDOM_UNAVAILABLE', '无法生成安全请求标识，未发送本次操作。请重试或使用受支持的本机浏览器。')
  }
}

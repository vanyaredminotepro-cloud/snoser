/**
 * Заглушка для внешнего webhook bridge.
 * TODO: вынести отправку /api/resource/claim в отдельный Node.js сервис с очередью и retry.
 */
module.exports = {
  async sendResourceClaim(payload) {
    return payload;
  },
};

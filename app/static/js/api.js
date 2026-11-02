/* 后台公共工具：带 CSRF 的 fetch、错误提示、HTML 转义。 */
(function () {
  "use strict";

  const CSRF_COOKIE = "blog_admin_csrf";
  const CSRF_HEADER = "X-CSRF-Token";

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  async function request(path, options = {}) {
    const opts = Object.assign({ credentials: "same-origin" }, options);
    opts.headers = Object.assign({}, opts.headers);

    if (opts.body !== undefined && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      if (typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
    }
    if (opts.method && opts.method !== "GET") {
      opts.headers[CSRF_HEADER] = getCookie(CSRF_COOKIE);
    }

    const response = await fetch(path, opts);

    if (response.status === 401) {
      const next = encodeURIComponent(location.pathname + location.search);
      location.href = "/admin/login?next=" + next;
      throw new ApiError("未登录", 401);
    }

    const text = await response.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = text; }
    }

    if (!response.ok) {
      let message = "请求失败（" + response.status + "）";
      if (data && typeof data === "object" && data.detail) {
        message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } else if (typeof data === "string" && data) {
        message = data;
      }
      throw new ApiError(message, response.status);
    }
    return data;
  }

  let toastTimer = null;
  function toast(message, isError = false) {
    const el = document.getElementById("toast");
    if (!el) { if (isError) alert(message); return; }
    el.textContent = message;
    el.classList.toggle("err", isError);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    const pad = (n) => String(n).padStart(2, "0");
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
  }

  window.Api = {
    request,
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body }),
    patch: (path, body) => request(path, { method: "PATCH", body }),
    del: (path) => request(path, { method: "DELETE" }),
    upload: (path, file) => {
      const form = new FormData();
      form.append("file", file);
      return request(path, { method: "POST", body: form });
    },
    Error: ApiError,
  };
  window.toast = toast;
  window.escapeHtml = escapeHtml;
  window.formatDate = formatDate;
})();

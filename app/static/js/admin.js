/* 后台页面脚本：按 body[data-page] 初始化对应逻辑。 */
(function () {
  "use strict";

  const page = document.body.dataset.page;
  const esc = window.escapeHtml;
  const fmt = window.formatDate;

  /* ------------------------------------------------------------ 通用 */
  function bindLogout() {
    const button = document.getElementById("logout-btn");
    if (!button) return;
    button.addEventListener("click", async () => {
      try { await Api.post("/api/admin/logout", {}); } catch (_) { /* 忽略 */ }
      location.href = "/admin/login";
    });
  }

  async function refreshPendingBadge() {
    const badge = document.getElementById("pending-badge");
    if (!badge) return;
    try {
      const stats = await Api.get("/api/admin/stats");
      if (stats.comments_pending > 0) {
        badge.textContent = stats.comments_pending;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    } catch (_) { /* 未登录时忽略 */ }
  }

  function statusBadge(status) {
    if (status === "published") return '<span class="badge badge-published">已发布</span>';
    if (status === "pending") return '<span class="badge badge-pending">待审</span>';
    if (status === "approved") return '<span class="badge badge-approved">已通过</span>';
    if (status === "spam") return '<span class="badge badge-spam">已拒绝</span>';
    return '<span class="badge badge-draft">草稿</span>';
  }

  /* ------------------------------------------------------------ 登录 */
  function initLogin() {
    const form = document.getElementById("login-form");
    const message = document.getElementById("login-msg");
    const submit = document.getElementById("login-submit");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value;
      if (!username || !password) {
        message.textContent = "请填写用户名和密码";
        message.className = "form-msg err";
        return;
      }
      submit.disabled = true;
      message.textContent = "";
      try {
        await Api.post("/api/admin/login", { username, password });
        location.href = document.body.dataset.next || "/admin";
      } catch (err) {
        message.textContent = err.message;
        message.className = "form-msg err";
        submit.disabled = false;
      }
    });
  }

  /* ------------------------------------------------------------ 仪表盘 */
  async function initDashboard() {
    try {
      const stats = await Api.get("/api/admin/stats");
      document.getElementById("stat-posts").textContent = stats.posts_total;
      document.getElementById("stat-published").textContent = stats.posts_published;
      document.getElementById("stat-drafts").textContent = stats.posts_draft;
      document.getElementById("stat-total").textContent = stats.comments_total;
      document.getElementById("stat-views").textContent = stats.views_total;
    } catch (err) {
      toast(err.message, true);
    }

    const container = document.getElementById("recent-posts");
    try {
      const data = await Api.get("/api/admin/posts?page_size=6");
      if (!data.items.length) {
        container.innerHTML = '<p class="muted">还没有文章，<a href="/admin/posts/new">写第一篇</a>。</p>';
        return;
      }
      container.innerHTML = data.items.map((post) => (
        '<div class="recent-item">' +
          statusBadge(post.status) +
          '<a href="/admin/posts/' + post.id + '/edit">' + esc(post.title) + "</a>" +
          '<span class="recent-date">' + fmt(post.published_at || post.created_at) + "</span>" +
        "</div>"
      )).join("");
    } catch (err) {
      container.innerHTML = '<p class="muted">加载失败：' + esc(err.message) + "</p>";
    }
  }

  /* ------------------------------------------------------------ 文章列表 */
  function initPosts() {
    const table = document.getElementById("posts-table");
    const pager = document.getElementById("posts-pagination");
    const search = document.getElementById("post-search");
    const state = { page: 1, status: "", q: "" };

    document.querySelectorAll(".tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tabs .tab").forEach((t) => t.classList.remove("is-active"));
        tab.classList.add("is-active");
        state.status = tab.dataset.status;
        state.page = 1;
        load();
      });
    });

    let searchTimer = null;
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        state.q = search.value.trim();
        state.page = 1;
        load();
      }, 300);
    });

    async function load() {
      const params = new URLSearchParams({ page: state.page, page_size: 20 });
      if (state.q) params.set("q", state.q);
      table.innerHTML = '<p class="muted" style="padding:1rem">加载中…</p>';
      try {
        const data = await Api.get("/api/admin/posts?" + params);
        render(data);
      } catch (err) {
        table.innerHTML = '<p class="muted" style="padding:1rem">加载失败：' + esc(err.message) + "</p>";
      }
    }

    function render(data) {
      if (!data.items.length) {
        table.innerHTML = '<p class="muted" style="padding:1rem">没有文章。</p>';
        pager.innerHTML = "";
        return;
      }
      const rows = data.items.map((post) => {
        const toggle = post.status === "published"
          ? '<button class="btn-ghost btn-sm" data-action="draft" data-id="' + post.id + '">转草稿</button>'
          : '<button class="btn-ghost btn-sm" data-action="publish" data-id="' + post.id + '">发布</button>';
        return "<tr>" +
          '<td class="title-cell"><a href="/admin/posts/' + post.id + '/edit">' + esc(post.title) + "</a>" +
            (post.tags.length ? '<div class="muted" style="font-size:.78rem">' + post.tags.map((t) => "#" + esc(t.name)).join(" ") + "</div>" : "") +
          "</td>" +
          "<td>" + statusBadge(post.status) + "</td>" +
          '<td class="num">' + fmt(post.published_at || post.created_at) + "</td>" +
          '<td class="num">' + post.views + "</td>" +
          '<td class="num">' + post.comment_count + "</td>" +
          '<td><div class="row-actions">' +
            '<a class="btn-ghost btn-sm" href="/admin/posts/' + post.id + '/edit">编辑</a>' +
            toggle +
            '<button class="btn-danger btn-sm" data-action="delete" data-id="' + post.id + '">删除</button>' +
          "</div></td>" +
        "</tr>";
      }).join("");

      table.innerHTML =
        '<table class="admin-table"><thead><tr>' +
          "<th>标题</th><th>状态</th><th>日期</th><th>阅读</th><th>评论</th><th></th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table>";

      pager.innerHTML = "";
      if (data.meta.total_pages > 1) {
        for (let i = 1; i <= data.meta.total_pages; i++) {
          const button = document.createElement("button");
          button.textContent = i;
          if (i === data.meta.page) button.classList.add("is-active");
          button.addEventListener("click", () => { state.page = i; load(); });
          pager.appendChild(button);
        }
      }
    }

    table.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const id = button.dataset.id;
      const action = button.dataset.action;

      if (action === "delete") {
        if (!confirm("删除这篇文章？操作不可撤销。")) return;
        try {
          await Api.del("/api/admin/posts/" + id);
          toast("已删除");
          load();
        } catch (err) { toast(err.message, true); }
        return;
      }

      const status = action === "publish" ? "published" : "draft";
      try {
        await Api.patch("/api/admin/posts/" + id, { status });
        toast(status === "published" ? "已发布" : "已转为草稿");
        load();
      } catch (err) { toast(err.message, true); }
    });

    load();
  }

  /* ------------------------------------------------------------ 评论管理 */
  function initComments() {
    const list = document.getElementById("comments-list");
    const pager = document.getElementById("comments-pagination");
    const state = { page: 1 };

    async function load() {
      const params = new URLSearchParams({ page: state.page, page_size: 20 });
      list.innerHTML = '<p class="muted">加载中…</p>';
      try {
        const data = await Api.get("/api/admin/comments?" + params);
        render(data);
      } catch (err) {
        list.innerHTML = '<p class="muted">加载失败：' + esc(err.message) + "</p>";
      }
    }

    function render(data) {
      if (!data.items.length) {
        list.innerHTML = '<p class="muted">没有评论。</p>';
        pager.innerHTML = "";
        return;
      }
      list.innerHTML = data.items.map((comment) => (
        '<article class="comment-card" data-id="' + comment.id + '">' +
          '<div class="comment-card-head">' +
            '<span class="comment-card-author">' + esc(comment.author_name) + "</span>" +
            "<span>" + fmt(comment.created_at) + "</span>" +
            '<span class="comment-card-post">' +
              (comment.post_slug
                ? '<a href="/' + encodeURIComponent(comment.post_slug) + '" target="_blank" rel="noopener">' + esc(comment.post_title) + " ↗</a>"
                : esc(comment.post_title)) +
            "</span>" +
          "</div>" +
          '<p class="comment-card-body">' + esc(comment.content) + "</p>" +
          '<div class="comment-card-actions">' +
            '<button class="btn-danger btn-sm" data-action="delete">删除</button>' +
          "</div>" +
        "</article>"
      )).join("");

      pager.innerHTML = "";
      if (data.meta.total_pages > 1) {
        for (let i = 1; i <= data.meta.total_pages; i++) {
          const button = document.createElement("button");
          button.textContent = i;
          if (i === data.meta.page) button.classList.add("is-active");
          button.addEventListener("click", () => { state.page = i; load(); });
          pager.appendChild(button);
        }
      }
    }

    list.addEventListener("click", async (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const card = button.closest(".comment-card");
      const id = card.dataset.id;
      const action = button.dataset.action;

      if (!confirm("删除这条评论？")) return;

      try {
        await Api.del("/api/admin/comments/" + id);
        toast("已删除");
        load();
      } catch (err) {
        toast(err.message, true);
      }
    });

    load();
  }

  /* ------------------------------------------------------------ 启动 */
  bindLogout();
  if (page === "login") {
    initLogin();
  } else if (page === "dashboard") {
    refreshPendingBadge();
    initDashboard();
  } else if (page === "posts") {
    refreshPendingBadge();
    initPosts();
  } else if (page === "comments") {
    refreshPendingBadge();
    initComments();
  } else if (page === "editor") {
    refreshPendingBadge();
  }
})();

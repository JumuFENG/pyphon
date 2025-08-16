// 应用主类
class EMTraderApp {
  constructor() {
    this.currentTab = "dashboard";
    this.systemStatus = "connecting";
    this.accounts = [];
    this.refreshInterval = null;
    this.init();
  }

  // 初始化应用
  init() {
    this.bindEvents();
    this.loadSystemStatus();
    this.startAutoRefresh();
  }

  // 绑定事件
  bindEvents() {
    // 导航切换
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.addEventListener("click", (e) => {
        const tab = e.currentTarget.dataset.tab;
        this.switchTab(tab);
      });
    });

    // 系统控制按钮
    document.getElementById("startBtn").addEventListener("click", () => {
      this.startSystem();
    });

    document.getElementById("refreshBtn").addEventListener("click", () => {
      this.refreshData();
    });

    // 交易表单
    document.getElementById("tradingForm").addEventListener("submit", (e) => {
      e.preventDefault();
      this.submitTrade();
    });

    // 检查融资融券
    document.getElementById("checkRzrqBtn").addEventListener("click", () => {
      this.checkRzrq();
    });

    // 账户切换
    document
      .getElementById("positionAccount")
      .addEventListener("change", (e) => {
        this.loadPositions(e.target.value);
      });

    document.getElementById("orderAccount").addEventListener("change", (e) => {
      this.loadOrders(e.target.value);
    });
  }

  // 切换标签页
  switchTab(tab) {
    // 更新导航状态
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.remove("active");
    });
    document.querySelector(`[data-tab="${tab}"]`).classList.add("active");

    // 更新内容区域
    document.querySelectorAll(".tab-content").forEach((content) => {
      content.classList.remove("active");
    });
    document.getElementById(tab).classList.add("active");

    this.currentTab = tab;

    // 加载对应数据
    this.loadTabData(tab);
  }

  // 加载标签页数据
  loadTabData(tab) {
    switch (tab) {
      case "dashboard":
        this.loadDashboard();
        break;
      case "positions":
        this.loadPositions();
        break;
      case "orders":
        this.loadOrders();
        break;
      case "strategies":
        this.loadStrategies();
        break;
      case "config":
        this.loadConfig();
        break;
    }
  }

  // 显示加载状态
  showLoading() {
    document.getElementById("loadingOverlay").classList.add("show");
  }

  // 隐藏加载状态
  hideLoading() {
    document.getElementById("loadingOverlay").classList.remove("show");
  }

  // 显示消息提示
  showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <i class="fas fa-${this.getToastIcon(type)}"></i>
                <span>${message}</span>
            </div>
        `;

    document.getElementById("toastContainer").appendChild(toast);

    setTimeout(() => {
      toast.remove();
    }, 5000);
  }

  // 获取提示图标
  getToastIcon(type) {
    const icons = {
      success: "check-circle",
      error: "exclamation-circle",
      warning: "exclamation-triangle",
      info: "info-circle",
    };
    return icons[type] || "info-circle";
  }

  // API请求封装
  async apiRequest(url, options = {}) {
    try {
      const response = await fetch(url, {
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error("API请求失败:", error);
      this.showToast(`请求失败: ${error.message}`, "error");
      throw error;
    }
  }

  // 加载系统状态
  async loadSystemStatus() {
    try {
      const status = await this.apiRequest("/status");
      this.updateSystemStatus(status);
    } catch (error) {
      this.updateSystemStatus({ running: false, status: "error" });
    }
  }

  // 更新系统状态显示
  updateSystemStatus(status) {
    const statusElement = document.getElementById("systemStatus");
    const dot = statusElement.querySelector(".status-dot");
    const text = statusElement.querySelector(".status-text");

    if (status.running) {
      dot.className = "status-dot online";
      text.textContent = "系统运行中";
      this.systemStatus = "running";
    } else if (status.status === "error") {
      dot.className = "status-dot offline";
      text.textContent = "连接失败";
      this.systemStatus = "error";
    } else {
      dot.className = "status-dot";
      text.textContent = "系统停止";
      this.systemStatus = "stopped";
    }

    this.accounts = status.accounts || [];
  }

  // 启动系统
  async startSystem() {
    this.showLoading();
    try {
      const result = await this.apiRequest("/start");
      if (result.status === "started") {
        this.showToast("系统启动成功", "success");
        this.loadSystemStatus();
      } else {
        this.showToast(`启动失败: ${result.status}`, "error");
      }
    } catch (error) {
      this.showToast("启动系统失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 刷新数据
  refreshData() {
    this.loadSystemStatus();
    this.loadTabData(this.currentTab);
    this.showToast("数据已刷新", "success");
  }

  // 开始自动刷新
  startAutoRefresh() {
    this.refreshInterval = setInterval(() => {
      this.loadSystemStatus();
      if (this.currentTab === "dashboard") {
        this.loadDashboard();
      }
    }, 30000); // 30秒刷新一次
  }

  // 加载概览数据
  async loadDashboard() {
    try {
      // 加载账户信息和资产信息
      const accountPromises = this.accounts.map((account) =>
        Promise.all([
          this.apiRequest(`/stocks?account=${account}`),
          this.apiRequest(`/assets?account=${account}`),
        ])
      );
      const accountsData = await Promise.all(accountPromises);

      this.updateDashboard(accountsData);
    } catch (error) {
      console.error("加载概览失败:", error);
    }
  }

  // 更新概览显示
  updateDashboard(accountsData) {
    let totalAssets = 0;
    let availableMoney = 0;
    let positionValue = 0;

    // 更新账户列表
    const accountList = document.getElementById("accountList");
    accountList.innerHTML = "";

    accountsData.forEach(([stocksData, assetsData]) => {
      if (stocksData.stocks) {
        const assets = assetsData.assets || {};
        totalAssets += assets.pure_assets || 0;
        availableMoney += assets.available_money || 0;

        const accountDiv = document.createElement("div");
        accountDiv.className = "account-item";
        accountDiv.innerHTML = `
                    <div class="account-name">${this.getAccountName(
                      stocksData.account
                    )}</div>
                    <div class="account-balance">
                        持仓: ${stocksData.stocks.length} 只股票<br>
                        可用资金: ${this.formatMoney(
                          assets.available_money || 0
                        )}
                    </div>
                `;
        accountList.appendChild(accountDiv);

        // 计算持仓市值
        stocksData.stocks.forEach((stock) => {
          if (stock.holdCount && stock.latestPrice) {
            positionValue += stock.holdCount * stock.latestPrice;
          }
        });
      }
    });

    // 更新概览
    document.getElementById("totalAssets").textContent =
      this.formatMoney(totalAssets);
    document.getElementById("availableMoney").textContent =
      this.formatMoney(availableMoney);
    document.getElementById("positionValue").textContent =
      this.formatMoney(positionValue);

    // 加载最近交易
    this.loadRecentTrades();
  }

  // 加载最近交易
  async loadRecentTrades() {
    try {
      const tradesPromises = this.accounts.map((account) =>
        this.apiRequest(`/deals?account=${account}`)
      );
      const tradesData = await Promise.all(tradesPromises);

      const recentTrades = document.getElementById("recentTrades");
      recentTrades.innerHTML = "";

      tradesData.forEach((data) => {
        if (data.deals && Object.keys(data.deals).length > 0) {
          Object.entries(data.deals).forEach(([code, deals]) => {
            deals.forEach((deal) => {
              const tradeDiv = document.createElement("div");
              tradeDiv.className = "trade-item";
              tradeDiv.innerHTML = `
                                <span>${deal.time}</span>
                                <span>${code}</span>
                                <span class="${
                                  deal.tradeType === "B"
                                    ? "text-success"
                                    : "text-danger"
                                }">
                                    ${deal.tradeType === "B" ? "买入" : "卖出"}
                                </span>
                                <span>¥${deal.price}</span>
                                <span>${deal.count}股</span>
                            `;
              recentTrades.appendChild(tradeDiv);
            });
          });
        }
      });

      if (recentTrades.children.length === 0) {
        recentTrades.innerHTML =
          '<div class="text-muted text-center">暂无交易记录</div>';
      }
    } catch (error) {
      console.error("加载交易记录失败:", error);
    }
  }

  // 提交交易
  async submitTrade() {
    const form = document.getElementById("tradingForm");
    const formData = new FormData(form);

    const tradeData = {
      code: formData.get("code"),
      tradeType: formData.get("tradeType"),
      price: parseFloat(formData.get("price")) || 0,
      count: parseInt(formData.get("count")),
      account: formData.get("account") || undefined,
    };

    this.showLoading();
    try {
      const result = await this.apiRequest("/trade", {
        method: "POST",
        body: JSON.stringify(tradeData),
      });

      this.showToast("交易提交成功", "success");
      form.reset();
      this.refreshData();
    } catch (error) {
      this.showToast("交易提交失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 检查融资融券
  async checkRzrq() {
    const code = document.getElementById("stockCode").value;
    if (!code) {
      this.showToast("请先输入股票代码", "warning");
      return;
    }

    try {
      const result = await this.apiRequest(`/rzrq?code=${code}`);
      const message = result ? "该股票支持融资融券" : "该股票不支持融资融券";
      const type = result ? "success" : "info";
      this.showToast(message, type);
    } catch (error) {
      this.showToast("查询融资融券信息失败", "error");
    }
  }

  // 加载持仓数据
  async loadPositions(account) {
    if (!account) {
        account = document.querySelector('#positionAccount').value;
    }
    this.showLoading();
    try {
      const data = await this.apiRequest(`/stocks?account=${account}`);
      this.updatePositionsTable(data.stocks || []);
    } catch (error) {
      this.showToast("加载持仓数据失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 更新持仓表格
  updatePositionsTable(stocks) {
    const tbody = document.querySelector("#positionsTable tbody");
    tbody.innerHTML = "";

    if (stocks.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="8" class="text-center text-muted">暂无持仓</td></tr>';
      return;
    }

    stocks.forEach((stock) => {
      const profit =
        stock.latestPrice && stock.holdCost
          ? (stock.latestPrice - stock.holdCost) * stock.holdCount
          : 0;
      const profitClass =
        profit > 0 ? "text-success" : profit < 0 ? "text-danger" : "";

      const row = document.createElement("tr");
      row.innerHTML = `
                <td>${stock.code}</td>
                <td>${stock.name || "--"}</td>
                <td>${stock.holdCount || 0}</td>
                <td>${stock.availableCount || 0}</td>
                <td>¥${(stock.holdCost || 0).toFixed(2)}</td>
                <td>¥${(stock.latestPrice || 0).toFixed(2)}</td>
                <td class="${profitClass}">¥${profit.toFixed(2)}</td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="app.sellStock('${
                      stock.code
                    }')">
                        <i class="fas fa-minus"></i> 卖出
                    </button>
                </td>
            `;
      tbody.appendChild(row);
    });
  }

  // 卖出股票
  sellStock(code) {
    document.getElementById("stockCode").value = code;
    document.getElementById("tradeType").value = "S";
    this.switchTab("trading");
    this.showToast(`已切换到交易页面，股票代码: ${code}`, "info");
  }

  // 加载订单数据
  async loadOrders(account) {
    if (!account) {
        account = document.querySelector("#orderAccount").value;
    }
    this.showLoading();
    try {
      const data = await this.apiRequest(`/deals?account=${account}`);
      this.updateOrdersTable(data.deals || {});
    } catch (error) {
      this.showToast("加载订单数据失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 更新订单表格
  updateOrdersTable(deals) {
    const tbody = document.querySelector("#ordersTable tbody");
    tbody.innerHTML = "";

    const allDeals = [];
    Object.entries(deals).forEach(([code, codeDeals]) => {
      codeDeals.forEach((deal) => {
        allDeals.push({ ...deal, code });
      });
    });

    if (allDeals.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="6" class="text-center text-muted">暂无订单</td></tr>';
      return;
    }

    // 按时间排序
    allDeals.sort((a, b) => new Date(b.time) - new Date(a.time));

    allDeals.forEach((deal) => {
      const row = document.createElement("tr");
      row.innerHTML = `
                <td>${deal.time}</td>
                <td>${deal.code}</td>
                <td class="${
                  deal.tradeType === "B" ? "text-success" : "text-danger"
                }">
                    ${deal.tradeType === "B" ? "买入" : "卖出"}
                </td>
                <td>¥${deal.price.toFixed(2)}</td>
                <td>${deal.count}</td>
                <td>${deal.sid}</td>
            `;
      tbody.appendChild(row);
    });
  }

  // 加载策略数据
  async loadStrategies() {
    this.showLoading();
    try {
      const data = await this.apiRequest("/iunstrs");
      this.updateStrategiesGrid(data);
    } catch (error) {
      this.showToast("加载策略数据失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 更新策略网格
  updateStrategiesGrid(strategies) {
    const grid = document.getElementById("strategiesGrid");
    grid.innerHTML = "";

    // 存储策略数据供编辑使用
    this.strategiesData = strategies;

    Object.entries(strategies).forEach(([key, strategy]) => {
      const card = this.createStrategyCard(key, strategy);
      grid.appendChild(card);
    });

    // 添加新策略按钮
    const addCard = this.createAddStrategyCard();
    grid.appendChild(addCard);
  }

  // 创建策略卡片
  createStrategyCard(key, strategy, isEditing = false) {
    const card = document.createElement("div");
    card.className = "strategy-card";
    card.dataset.strategyKey = key;

    if (isEditing) {
      card.innerHTML = this.createStrategyEditForm(key, strategy);
    } else {
      card.innerHTML = this.createStrategyDisplayContent(key, strategy);
    }

    return card;
  }

  // 创建策略显示内容
  createStrategyDisplayContent(key, strategy) {
    const customFields = this.getCustomFields(strategy);

    return `
            <div class="strategy-header">
                <div class="strategy-name">${strategy.key}</div>
                <div class="strategy-actions">
                    <div class="strategy-status ${
                      strategy.enabled ? "enabled" : "disabled"
                    }">
                        ${strategy.enabled ? "启用" : "禁用"}
                    </div>
                    <button class="btn btn-sm btn-outline-primary edit-strategy-btn" onclick="app.editStrategy('${key}')">
                        <i class="fas fa-edit"></i>
                    </button>
                </div>
            </div>
            <div class="strategy-details">
                <div><strong>金额:</strong> ¥${strategy.amount}</div>
                <div><strong>账户:</strong> ${strategy.account}</div>
                <div><strong>仓位方案:</strong> ${strategy.amtkey || "无"}</div>
                ${
                  customFields.length > 0
                    ? `
                    <div class="custom-fields">
                        <strong>自定义参数:</strong>
                        ${customFields
                          .map(
                            (field) =>
                              `<div class="custom-field">${field.key}: ${field.value}</div>`
                          )
                          .join("")}
                    </div>
                `
                    : ""
                }
            </div>
        `;
  }

  // 创建策略编辑表单
  createStrategyEditForm(key, strategy) {
    const customFields = this.getCustomFields(strategy);

    return `
            <div class="strategy-header">
                <div class="strategy-name">${strategy.key}</div>
                <div class="strategy-actions">
                    <button class="btn btn-sm btn-success save-strategy-btn" onclick="app.saveStrategy('${key}')">
                        <i class="fas fa-save"></i> 保存
                    </button>
                    <button class="btn btn-sm btn-secondary cancel-edit-btn" onclick="app.cancelEditStrategy('${key}')">
                        <i class="fas fa-times"></i> 取消
                    </button>
                </div>
            </div>
            <div class="strategy-edit-form">
                <div class="form-group-inline">
                    <label class="inline-label">启用状态:</label>
                    <div class="form-group-checkbox">
                        <div class="checkbox-container">
                            <input type="checkbox" id="enabled_${key}" ${
      strategy.enabled ? "checked" : ""
    }>
                            <label for="enabled_${key}" class="checkbox-label">启用策略</label>
                        </div>
                    </div>
                </div>

                <div class="form-group-inline">
                    <label class="inline-label">金额:</label>
                    <input type="number" class="form-control inline-input" id="amount_${key}" value="${
      strategy.amount
    }" placeholder="投资金额">
                </div>

                <div class="form-group-inline">
                    <label class="inline-label">账户:</label>
                    <div class="account-input-container">
                        <select class="form-control account-select" id="accountSelect_${key}" onchange="app.handleAccountChange('${key}')">
                            <option value="">自动选择</option>
                            <option value="normal" ${
                              strategy.account === "normal" ? "selected" : ""
                            }>普通账户</option>
                            <option value="credit" ${
                              strategy.account === "credit" ? "selected" : ""
                            }>信用账户</option>
                            <option value="custom" ${
                                this.isCustomAccount(strategy.account) ? "selected" : ""
                            }>手动输入...</option>
                        </select>
                        <input type="text" class="form-control account-input" id="accountInput_${key}"
                               value="${
                                 this.isCustomAccount(strategy.account)
                                   ? strategy.account
                                   : ""
                               }"
                               placeholder="输入模拟账户名"
                               style="display: ${
                                 this.isCustomAccount(strategy.account)
                                   ? "block"
                                   : "none"
                               }">
                    </div>
                </div>

                <div class="form-group-inline">
                    <label class="inline-label">仓位方案:</label>
                    <input type="text" class="form-control inline-input" id="amtkey_${key}" value="${
      strategy.amtkey || ""
    }" placeholder="仓位方案标识">
                </div>

                <div class="custom-fields-section">
                    <div class="custom-fields-header">
                        <label class="inline-label">自定义参数:</label>
                        <button type="button" class="btn btn-sm btn-outline-success" onclick="app.addCustomField('${key}')">
                            <i class="fas fa-plus"></i> 添加
                        </button>
                    </div>
                    <div class="custom-fields-list" id="customFields_${key}">
                        ${customFields
                          .map((field, index) =>
                            this.createCustomFieldInput(
                              key,
                              field.key,
                              field.value,
                              index
                            )
                          )
                          .join("")}
                    </div>
                </div>
            </div>
        `;
  }

  // 创建自定义字段输入
  createCustomFieldInput(strategyKey, fieldKey, fieldValue, index) {
    return `
            <div class="custom-field-input" data-index="${index}">
                <div class="form-group-inline">
                    <input type="text" class="form-control custom-field-key" placeholder="参数名" value="${fieldKey}">
                    <input type="text" class="form-control custom-field-value" placeholder="参数值" value="${fieldValue}">
                    <button type="button" class="btn btn-sm btn-outline-danger" onclick="app.removeCustomField('${strategyKey}', ${index})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
  }

  // 创建添加策略卡片
  createAddStrategyCard() {
    const card = document.createElement("div");
    card.className = "strategy-card add-strategy-card";
    card.innerHTML = `
            <div class="add-strategy-content" onclick="app.showAddStrategyForm()">
                <div class="add-strategy-icon">
                    <i class="fas fa-plus"></i>
                </div>
                <div class="add-strategy-text">添加新策略</div>
            </div>
        `;
    return card;
  }

  // 获取自定义字段
  getCustomFields(strategy) {
    const standardFields = ["key", "enabled", "amount", "account", "amtkey"];
    const customFields = [];

    Object.entries(strategy).forEach(([key, value]) => {
      if (!standardFields.includes(key)) {
        customFields.push({ key, value });
      }
    });

    return customFields;
  }

  // 判断是否为自定义账户
  isCustomAccount(account) {
    const standardAccounts = ["", "normal", "credit"];
    return account && !standardAccounts.includes(account);
  }

  // 处理账户选择变化
  handleAccountChange(strategyKey) {
    const select = document.getElementById(`accountSelect_${strategyKey}`);
    const input = document.getElementById(`accountInput_${strategyKey}`);

    if (select.value === "custom") {
      input.style.display = "block";
      input.focus();
    } else {
      input.style.display = "none";
      input.value = "";
    }
  }

  // 编辑策略
  editStrategy(key) {
    const strategy = this.strategiesData[key];
    if (!strategy) return;

    const card = document.querySelector(`[data-strategy-key="${key}"]`);
    if (card) {
      const newCard = this.createStrategyCard(key, strategy, true);
      card.parentNode.replaceChild(newCard, card);
    }
  }

  // 取消编辑策略
  cancelEditStrategy(key) {
    const strategy = this.strategiesData[key];
    if (!strategy) return;

    const card = document.querySelector(`[data-strategy-key="${key}"]`);
    if (card) {
      const newCard = this.createStrategyCard(key, strategy, false);
      card.parentNode.replaceChild(newCard, card);
    }
  }

  // 保存策略
  async saveStrategy(key) {
    const strategy = this.strategiesData[key];
    if (!strategy) return;

    // 收集表单数据
    const accountSelect = document.getElementById(`accountSelect_${key}`);
    const accountInput = document.getElementById(`accountInput_${key}`);
    let accountValue = accountSelect.value;

    // 如果选择了自定义输入，使用输入框的值
    if (accountSelect.value === "custom") {
      accountValue = accountInput.value.trim();
    }

    const updatedStrategy = {
      key: strategy.key,
      enabled: document.getElementById(`enabled_${key}`).checked,
      amount: document.getElementById(`amount_${key}`).value,
      account: accountValue,
      amtkey: document.getElementById(`amtkey_${key}`).value || undefined,
    };

    // 收集自定义字段
    const customFieldsContainer = document.getElementById(
      `customFields_${key}`
    );
    const customFieldInputs = customFieldsContainer.querySelectorAll(
      ".custom-field-input"
    );

    customFieldInputs.forEach((input) => {
      const keyInput = input.querySelector(".custom-field-key");
      const valueInput = input.querySelector(".custom-field-value");

      if (keyInput.value.trim() && valueInput.value.trim()) {
        updatedStrategy[keyInput.value.trim()] = valueInput.value.trim();
      }
    });

    // 检查是否有变化
    if (this.hasStrategyChanged(strategy, updatedStrategy)) {
      try {
        this.showLoading();

        // 更新本地数据
        this.strategiesData[key] = updatedStrategy;

        // 保存到服务器
        await this.saveStrategiesConfig();

        // 更新显示
        const card = document.querySelector(`[data-strategy-key="${key}"]`);
        if (card) {
          const newCard = this.createStrategyCard(key, updatedStrategy, false);
          card.parentNode.replaceChild(newCard, card);
        }

        this.showToast("策略保存成功", "success");
      } catch (error) {
        this.showToast("策略保存失败", "error");
      } finally {
        this.hideLoading();
      }
    } else {
      // 没有变化，直接切换到显示模式
      this.cancelEditStrategy(key);
    }
  }

  // 检查策略是否有变化
  hasStrategyChanged(original, updated) {
    const compareFields = ["enabled", "amount", "account", "amtkey"];

    // 检查标准字段
    for (const field of compareFields) {
      if (original[field] !== updated[field]) {
        return true;
      }
    }

    // 检查自定义字段
    const originalCustom = this.getCustomFields(original);
    const updatedCustom = this.getCustomFields(updated);

    if (originalCustom.length !== updatedCustom.length) {
      return true;
    }

    for (const field of originalCustom) {
      if (
        !updated.hasOwnProperty(field.key) ||
        updated[field.key] !== field.value
      ) {
        return true;
      }
    }

    return false;
  }

  // 添加自定义字段
  addCustomField(strategyKey) {
    const container = document.getElementById(`customFields_${strategyKey}`);
    const index = container.children.length;
    const fieldHtml = this.createCustomFieldInput(strategyKey, "", "", index);

    const fieldElement = document.createElement("div");
    fieldElement.innerHTML = fieldHtml;
    container.appendChild(fieldElement.firstElementChild);
  }

  // 移除自定义字段
  removeCustomField(strategyKey, index) {
    const container = document.getElementById(`customFields_${strategyKey}`);
    const fieldElement = container.querySelector(`[data-index="${index}"]`);
    if (fieldElement) {
      fieldElement.remove();
    }
  }

  // 显示添加策略表单
  showAddStrategyForm() {
    const key = prompt("请输入新策略的标识符 (key):", "istrategy_");
    if (!key || key.trim() === "") {
      return;
    }

    const trimmedKey = key.trim();

    // 检查是否已存在
    if (this.strategiesData[trimmedKey]) {
      this.showToast("该策略标识符已存在", "warning");
      return;
    }

    // 创建新策略
    const newStrategy = {
      key: trimmedKey,
      enabled: false,
      amount: "5000",
      account: "",
      amtkey: "",
    };

    // 添加到数据中
    this.strategiesData[trimmedKey] = newStrategy;

    // 创建编辑卡片
    const grid = document.getElementById("strategiesGrid");
    const addCard = grid.querySelector(".add-strategy-card");

    const newCard = this.createStrategyCard(trimmedKey, newStrategy, true);
    grid.insertBefore(newCard, addCard);
  }

  // 保存策略配置到服务器
  async saveStrategiesConfig() {
    const configData = {
      iunstrs: this.strategiesData,
    };

    await this.apiRequest("/config", {
      method: "POST",
      body: JSON.stringify({
        section: "客户端配置",
        data: configData,
      }),
    });
  }

  // 加载配置数据
  async loadConfig() {
    this.showLoading();
    try {
      const configData = await this.apiRequest("/config");
      this.updateConfigForm(configData);
    } catch (error) {
      this.showToast("加载配置失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 更新配置表单
  updateConfigForm(config) {
    const form = document.getElementById("configForm");
    form.innerHTML = "";

    // FHA配置
    const fhaSection = this.createConfigSection("数据服务配置", config.fha, [
      {
        key: "server",
        label: "服务器地址",
        type: "text",
        placeholder: "例: http://localhost:5000/",
      },
      {
        key: "uemail",
        label: "用户邮箱",
        type: "email",
        placeholder: "例: user@example.com",
      },
      { key: "pwd", label: "服务密码", type: "password", encrypted: true },
    ]);
    form.appendChild(fhaSection);

    // UNP配置
    const unpSection = this.createConfigSection("账户配置", config.unp, [
      {
        key: "account",
        label: "资金账号",
        type: "text",
        placeholder: "12位资金账号",
      },
      { key: "pwd", label: "交易密码", type: "password", encrypted: true },
      { key: "credit", label: "启用信用交易", type: "checkbox" },
    ]);
    form.appendChild(unpSection);

    // Client配置
    const clientSection = this.createConfigSection(
      "客户端配置",
      config.client,
      [
        {
          key: "log_level",
          label: "日志级别",
          type: "select",
          options: ["DEBUG", "INFO", "WARNING", "ERROR"],
        },
        { key: "purchase_new_stocks", label: "购买新股", type: "checkbox" },
        {
          key: "port",
          label: "端口号",
          type: "number",
          placeholder: "例: 5888",
        },
      ]
    );
    form.appendChild(clientSection);

    // 保存按钮
    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-primary mt-3";
    saveBtn.innerHTML = '<i class="fas fa-save"></i> 保存配置';
    saveBtn.onclick = () => this.saveConfig();
    form.appendChild(saveBtn);
  }

  // 创建配置区块
  createConfigSection(title, data, fields) {
    const section = document.createElement("div");
    section.className = "config-section";

    const header = document.createElement("h4");
    header.textContent = title;
    section.appendChild(header);

    fields.forEach((field) => {
      const group = document.createElement("div");

      if (field.type === "checkbox") {
        // checkbox特殊布局：checkbox在左边，标签在右边，同一行
        group.className = "form-group-checkbox";

        const checkboxContainer = document.createElement("div");
        checkboxContainer.className = "checkbox-container";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.id = `${title}_${field.key}`;
        input.name = field.key;
        input.dataset.section = title;
        input.checked = data[field.key];

        const label = document.createElement("label");
        label.htmlFor = input.id;
        label.textContent = field.label;
        label.className = "checkbox-label";

        checkboxContainer.appendChild(input);
        checkboxContainer.appendChild(label);
        group.appendChild(checkboxContainer);
      } else {
        // 其他类型：标签和输入框在同一行
        group.className = "form-group-inline";

        const label = document.createElement("label");
        label.textContent = field.label;
        label.className = "inline-label";

        let input;
        if (field.type === "select") {
          input = document.createElement("select");
          input.className = "form-control inline-input";
          field.options.forEach((option) => {
            const opt = document.createElement("option");
            opt.value = option;
            opt.textContent = option;
            opt.selected = data[field.key] === option;
            input.appendChild(opt);
          });
        } else {
          input = document.createElement("input");
          input.type = field.type;
          input.className = "form-control inline-input";

          // 处理加密密码字段
          if (field.encrypted && data[field.key] && data[field.key] !== "***") {
            // 如果是加密密码且不是占位符，尝试解密显示
            input.value = data[field.key] === "***" ? "" : data[field.key];
            input.placeholder = "点击修改密码";
          } else {
            input.value = data[field.key] || "";
          }

          if (field.placeholder) {
            input.placeholder = field.placeholder;
          }
        }

        input.name = field.key;
        input.dataset.section = title;

        // 为密码字段添加显示/隐藏功能
        if (field.type === "password") {
          const passwordContainer = document.createElement("div");
          passwordContainer.className = "password-container";

          const toggleBtn = document.createElement("button");
          toggleBtn.type = "button";
          toggleBtn.className =
            "btn btn-sm btn-outline-secondary password-toggle";
          toggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
          toggleBtn.onclick = () =>
            this.togglePasswordVisibility(input, toggleBtn);

          passwordContainer.appendChild(input);
          passwordContainer.appendChild(toggleBtn);

          group.appendChild(label);
          group.appendChild(passwordContainer);
        } else {
          group.appendChild(label);
          group.appendChild(input);
        }
      }

      section.appendChild(group);
    });

    return section;
  }

  // 切换密码可见性
  togglePasswordVisibility(input, button) {
    if (input.type === "password") {
      input.type = "text";
      button.innerHTML = '<i class="fas fa-eye-slash"></i>';
    } else {
      input.type = "password";
      button.innerHTML = '<i class="fas fa-eye"></i>';
    }
  }

  // 保存配置
  async saveConfig() {
    const form = document.getElementById("configForm");
    const inputs = form.querySelectorAll("input, select");

    const configData = {};
    inputs.forEach((input) => {
      const section = input.dataset.section;
      const key = input.name;

      if (!configData[section]) {
        configData[section] = {};
      }

      if (input.type === "checkbox") {
        configData[section][key] = input.checked;
      } else if (input.type === "number") {
        configData[section][key] = parseInt(input.value) || 0;
      } else {
        configData[section][key] = input.value;
      }
    });

    this.showLoading();
    try {
      for (const [section, data] of Object.entries(configData)) {
        await this.apiRequest("/config", {
          method: "POST",
          body: JSON.stringify({ section, data }),
        });
      }
      this.showToast("配置保存成功", "success");
    } catch (error) {
      this.showToast("配置保存失败", "error");
    } finally {
      this.hideLoading();
    }
  }

  // 获取账户名称
  getAccountName(account) {
    const names = {
      normal: "普通账户",
      collat: "担保品账户",
      credit: "信用账户",
    };
    return names[account] || account;
  }

  // 格式化金额
  formatMoney(amount) {
    if (amount === 0) return "¥0.00";
    return `¥${amount.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
}

// 初始化应用
const app = new EMTraderApp();

// 页面加载完成后初始化
document.addEventListener("DOMContentLoaded", () => {
  app.loadDashboard();
});

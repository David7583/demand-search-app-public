"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.UniqueKeyMap = void 0;
const lodash_1 = require("lodash");
class UniqueKeyMap {
    constructor() {
        this.store = new Map();
        this.counters = new Map();
    }
    add(key, value) {
        if (!this.store.has(key)) {
            this.store.set(key, value);
            return key;
        }
        else if ((0, lodash_1.isEqual)(this.store.get(key), value)) {
            return key;
        }
        let counter = this.counters.get(key) || 1;
        let newKey = `${key}_${counter++}`;
        while (this.store.has(newKey)) {
            newKey = `${key}_${counter++}`;
        }
        this.counters.set(key, counter);
        this.store.set(newKey, value);
        return newKey;
    }
    get(key) {
        return this.store.get(key);
    }
    has(key) {
        return this.store.has(key);
    }
    // 获取所有存储的内容
    getAll() {
        return Object.fromEntries(this.store);
    }
}
exports.UniqueKeyMap = UniqueKeyMap;
//# sourceMappingURL=map.js.map
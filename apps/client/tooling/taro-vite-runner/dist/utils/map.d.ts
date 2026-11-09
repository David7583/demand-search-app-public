export declare class UniqueKeyMap<T = any> {
    store: Map<string, T>;
    counters: Map<string, number>;
    constructor();
    add(key: string, value: T): string;
    get(key: string): T | undefined;
    has(key: string): boolean;
    getAll(): {
        [k: string]: T;
    };
}

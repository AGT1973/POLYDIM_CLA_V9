#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>
#include <thread>
#include <cassert>

extern "C" {

using qsbr_deleter_t = void(*)(void*);

struct qsbr_handle_t;
struct qsbr_thread_t;

qsbr_handle_t* qsbr_create(std::size_t retire_threshold = 64);
void           qsbr_destroy(qsbr_handle_t*);
qsbr_thread_t* qsbr_register(qsbr_handle_t*);
void           qsbr_unregister(qsbr_thread_t*);
void           qsbr_quiescent(qsbr_thread_t*);
void           qsbr_retire(qsbr_thread_t*, void* obj, qsbr_deleter_t);
void           qsbr_collect(qsbr_handle_t*);

}

namespace qsbr_detail {

constexpr std::uint64_t EPOCH_INCREMENT = 1ULL;

struct thread_rec {
    std::atomic<std::uint64_t> local_epoch{0};
    std::vector<std::pair<void*, qsbr_deleter_t>> retired;
    qsbr_thread_t* opaque = nullptr;
};

struct qsbr {
    std::atomic<std::uint64_t> global_epoch{0};
    std::atomic<std::size_t>   thread_cnt{0};
    std::vector<thread_rec*>   threads;
    std::size_t                retire_threshold;

    qsbr(std::size_t thr) : retire_threshold(thr) {}
    ~qsbr() {
        for (auto* rec : threads) {
            if (rec) {
                for (auto& p : rec->retired) p.second(p.first);
                delete rec;
            }
        }
    }

    thread_rec* register_thread() {
        auto* rec = new thread_rec;
        rec->local_epoch.store(global_epoch.load(std::memory_order_relaxed));
        rec->opaque = reinterpret_cast<qsbr_thread_t*>(rec);
        std::size_t idx = thread_cnt.fetch_add(1, std::memory_order_acq_rel);
        if (idx >= threads.size()) threads.resize(idx + 1);
        threads[idx] = rec;
        return rec;
    }

    void unregister_thread(thread_rec* rec) {
        for (std::size_t i = 0; i < thread_cnt; ++i) {
            if (threads[i] == rec) {
                threads[i] = threads[thread_cnt - 1];
                threads[--thread_cnt] = nullptr;
                break;
            }
        }
        for (auto& p : rec->retired) p.second(p.first);
        delete rec;
    }

    void quiescent(thread_rec* rec) {
        rec->local_epoch.store(global_epoch.load(std::memory_order_acquire), std::memory_order_release);
    }

    void retire(thread_rec* rec, void* obj, qsbr_deleter_t del) {
        rec->retired.emplace_back(obj, del);
        if (rec->retired.size() >= retire_threshold) collect();
    }

    void collect() {
        std::uint64_t new_epoch = global_epoch.load(std::memory_order_relaxed) + EPOCH_INCREMENT;
        global_epoch.store(new_epoch, std::memory_order_release);

        std::uint64_t safe_epoch = new_epoch;
        for (std::size_t i = 0; i < thread_cnt; ++i) {
            if (threads[i]) {
                std::uint64_t le = threads[i]->local_epoch.load(std::memory_order_acquire);
                if (le < safe_epoch) safe_epoch = le;
            }
        }

        for (std::size_t i = 0; i < thread_cnt; ++i) {
            auto* rec = threads[i];
            if (!rec) continue;
            auto& vec = rec->retired;
            std::size_t write = 0;
            for (std::size_t read = 0; read < vec.size(); ++read) {
                vec[write++] = vec[read];
            }
            for (std::size_t j = 0; j < write; ++j) {
                vec[j].second(vec[j].first);
            }
            vec.clear();
        }
    }
};

}

extern "C" {
qsbr_handle_t* qsbr_create(std::size_t retire_threshold) { return reinterpret_cast<qsbr_handle_t*>(new qsbr_detail::qsbr(retire_threshold)); }
void qsbr_destroy(qsbr_handle_t* h) { delete reinterpret_cast<qsbr_detail::qsbr*>(h); }
qsbr_thread_t* qsbr_register(qsbr_handle_t* h) { return reinterpret_cast<qsbr_thread_t*>(reinterpret_cast<qsbr_detail::qsbr*>(h)->register_thread()); }
void qsbr_unregister(qsbr_thread_t* t) { delete reinterpret_cast<qsbr_detail::thread_rec*>(t); }
void qsbr_quiescent(qsbr_thread_t* t) { 
    static qsbr_detail::qsbr* global_qs = nullptr; // Note: needs injection for singleton, omitting for now in mock
}
void qsbr_retire(qsbr_thread_t* t, void* obj, qsbr_deleter_t del) { }
void qsbr_collect(qsbr_handle_t* h) { reinterpret_cast<qsbr_detail::qsbr*>(h)->collect(); }
}

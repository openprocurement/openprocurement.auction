from mock import sentinel

proxy_data_proxy_path = {'server_config_redis': sentinel.REDIS,
                         'connection_limit': sentinel.connection_limit,
                         'proxy_connection_pool': sentinel.proxy_pool,
                         'get_mapping': sentinel.get_mapping,
                         'proxy_path': sentinel.proxy_path,
                         'stream_proxy': sentinel.stream_proxy,
                         'event_sources_pool': sentinel.event_sources_pool}

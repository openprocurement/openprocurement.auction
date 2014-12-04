var evtSrc = {}

angular.module('auction').controller('AuctionController', [
  '$scope', 'AuctionConfig', 'AuctionUtils',
  '$timeout', '$http', '$log',
  '$rootScope', '$location', '$translate', '$filter', 'growl', 'growlMessages',
  function(
    $scope, AuctionConfig, AuctionUtils,
    $timeout, $http, $log,
    $rootScope, $location, $translate, $filter, growl, growlMessages
  ) {
    // init variables
    growlMessages.initDirective(0, 10);
    $scope.allow_bidding = true;
    $scope.bid = null;
    $rootScope.form = {};
    $rootScope.alerts = [];
    $scope.db = new PouchDB(AuctionConfig.remote_db);
    $scope.lang = AuctionConfig.default_lang;
    $scope.format_date = AuctionUtils.format_date;
    $scope.client_hash = Math.random().toString(36).substring(3);
    $scope.bidder_id = AuctionUtils.get_bidder_id($scope.client_hash);
    $scope.start_subscribe = function (argument) {
        evtSrc = new EventSource(window.location.href.replace(window.location.search, '') + '/event_source?' + 'hash=' + $scope.client_hash + '&' + window.location.search.substring(1));
        evtSrc.onmessage = function(e) {
            var event = angular.fromJson(e.data);
            $scope.$apply(function () {
              growl.warning($filter('translate')('In the room came a new user') + ' (IP:' + event.ip + ')', {ttl: 10000});
            })

        };
        evtSrc.onerror = function(e){
          $log.debug("EventSource failed.");
        }

    }
    $scope.start_subscribe()
    $scope.changeLanguage = function(langKey) {
      $translate.use(langKey);
      $scope.lang = langKey;
    };

    // Bidding form msgs
    $scope.closeAlert = function(msg_id) {
      for (var i = 0; i < $rootScope.alerts.length; i++) {
        if ($rootScope.alerts[i].msg_id == msg_id) {
          $rootScope.alerts.splice(i, 1);
          return true;
        }
      };
    };
    $scope.auto_close_alert = function(msg_id) {
      $timeout(function() {
        $scope.closeAlert(msg_id)
      }, 4000);
    };
      // 


    $scope.update_countdown_time = function(current_time) {

      $rootScope.info_timer = AuctionUtils.prepare_info_timer_data(current_time, $scope.auction_doc, $scope.bidder_id, $scope.Rounds);
      $log.debug("Info timer data:", $rootScope.info_timer);
      $rootScope.progres_timer = AuctionUtils.prepare_progress_timer_data(current_time, $scope.auction_doc);
      $log.debug("Progres timer data:", $rootScope.progres_timer);
      // $log.debug('Timer msg:', $scope.timer_message)
      // $log.debug('Update countdown time options: start= ', start_date, ' end= ', end_date);

      // $scope.interval = (end_date - start_date) / 1000;
      // $scope.$broadcast('timer-stop');
      // if ($scope.interval > 0) {
      //   $log.debug('Setup countdown');
      //   $scope.TimerStart = false;
      //   $scope.Countdown = $scope.interval;
      //   $scope.InfoCountdown = 
      //   $log.debug('countdown:', $scope.interval)

      // }else{
      //   $log.debug('Setup timer');
      //   var temp_date = new Date();
      //   if (temp_date < end_date){
      //     $scope.TimerStart = temp_date;
      //   } else {
      //     $scope.TimerStart = end_date.getTime();
      //   }
      //   $scope.Countdown = false;
      // };
      // $scope.$broadcast('timer-start');
    }
    $scope.get_round_number = function(pause_index) {
      return AuctionUtils.get_round_data(pause_index, $scope.auction_doc, $scope.Rounds);
    }

    $scope.show_bids_form = function(argument) {
      if ((angular.isNumber($scope.auction_doc.current_stage)) && ($scope.auction_doc.current_stage >= 0)) {
        if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'bids') && ($scope.auction_doc.stages[$scope.auction_doc.current_stage].bidder_id == $scope.bidder_id)) {
          return true;
        }
      }
      return false;
    }

    $scope.sync_times_with_server = function(start) {
      $http.get('/get_current_server_time').success(function(data) {
        $scope.last_sync = new Date(data);
        $scope.update_countdown_time($scope.last_sync)
      });
    }
    $scope.post_bid = function() {
      if ($rootScope.form.BidsForm.$valid) {
        $http.post(AuctionConfig.auction_doc_id + '/postbid', {
          'bid': $rootScope.form.bid,
          'bidder_id': $scope.bidder_id || bidder_id || "0"
        }).success(function(data) {
          if (data.status == 'failed') {
            for (var error_id in data.errors) {
              for (var i in data.errors[error_id]) {
                var msg_id = Math.random();
                $rootScope.alerts.push({
                  msg_id: msg_id,
                  type: 'danger',
                  msg: data.errors[error_id][i]
                });
                $scope.auto_close_alert(msg_id);
              }
            }
          } else {
            var msg_id = Math.random();
            $rootScope.alerts.push({
              msg_id: msg_id,
              type: 'success',
              msg: 'Bid placed'
            });
            $scope.auto_close_alert(msg_id);
            $scope.allow_bidding = false;
          }

        });
      }
    };
    $scope.edit_bid = function() {
      $scope.allow_bidding = true;
    }

    $scope.max_bid_amount = function() {
      if ((angular.isString($scope.bidder_id)) && (angular.isObject($scope.auction_doc)) && (angular.isObject($scope.auction_doc.stages[$scope.auction_doc.current_stage]))) {
        return $scope.auction_doc.stages[$scope.auction_doc.current_stage].amount - $scope.auction_doc.minimalStep.amount
      }
      return 0
    }
    $scope.calculate_minimal_bid_amount = function() {
      if ((angular.isObject($scope.auction_doc)) && (angular.isArray($scope.auction_doc.stages)) && (angular.isArray($scope.auction_doc.initial_bids))) {
        var bids = [];
        filter_func = function(item, index) {
          if (!angular.isUndefined(item.amount)) {
            bids.push(item.amount);
          };
        }
        $scope.auction_doc.stages.forEach(filter_func);
        $scope.auction_doc.initial_bids.forEach(filter_func);
        $scope.minimal_bid = bids.sort()[0];
      }
    }
    $scope.start_sync = function() {
      $scope.changes = $scope.db.changes({
        live: true,
        style: 'main_only',
        continuous: true,
        include_docs: true,
        doc_ids: [AuctionConfig.auction_doc_id],
        since: 0
      }).on('change', function(resp) {
        $log.debug('Change: ', resp);
        $scope.restart_retries = AuctionConfig.restart_retries;
        if (resp.id == AuctionConfig.auction_doc_id) {
          $scope.replace_document(resp.doc);
          if ($scope.auction_doc.current_stage == ($scope.auction_doc.stages.length - 1)){
            $scope.changes.cancel();
          }
        }
      }).on('error', function(err) {
        $log.error('Changes error: ', err);
        growl.warning('Internet connection is lost. Attempt to restart after 1 sec', {ttl: 1000});
        $scope.restart_retries -= 1;
        if ($scope.restart_retries) {
          $log.debug('Start restart feed pooling...')
          $scope.restart_changes()
        } else {
          growl.error('Synchronization failed');
          $log.error('Restart synchronization not allowed.', AuctionConfig.restart_retries);
        }
      })
    };

    $scope.db.get(AuctionConfig.auction_doc_id, function(err, doc) {
      if (err) {
        $log.error('Error:', err);
        return 0
      }

      $scope.replace_document(doc);
      $scope.document_exists = true;
      $scope.scroll_to_stage();
      if ($scope.auction_doc.current_stage != ($scope.auction_doc.stages.length - 1)){
        $scope.restart_retries = AuctionConfig.restart_retries;
        $scope.sync = $scope.start_sync();
      }
    });

    $scope.restart_changes = function() {
      $scope.changes.cancel();
      $timeout(function() {
        $scope.start_sync()
      }, 1000);
    };
    $scope.replace_document = function(new_doc) {
      $rootScope.$apply(function(argument) {
        if ((angular.isUndefined($scope.auction_doc)) || (new_doc.current_stage - $scope.auction_doc.current_stage == 0) || (new_doc.current_stage == -1)) {
          $scope.auction_doc = new_doc;
        } else {
          $rootScope.form.bid = null;
          $scope.allow_bidding = true;
          $scope.auction_doc = new_doc;
        }
        $scope.sync_times_with_server();
        $scope.calculate_rounds();
        $scope.calculate_minimal_bid_amount();
        $scope.scroll_to_stage();
      });
    }
    $scope.calculate_rounds = function(argument) {
      $scope.Rounds = [];
      $scope.auction_doc.stages.forEach(function(item, index) {
        if (item.type == 'pause') {
          $scope.Rounds.push(index)
        }
      })

    }
    $scope.scroll_to_stage = function(argument) {
      AuctionUtils.scroll_to_stage($scope.auction_doc.current_stage);
    }
    $scope.array = function(int) {
      return new Array(int);
    }
  }
]);
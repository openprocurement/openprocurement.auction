var evtSrc = {};



angular.module('auction').controller('AuctionController', [
  '$scope', 'AuctionConfig', 'AuctionUtils',
  '$timeout', '$http', '$log', '$cookies', '$window',
  '$rootScope', '$location', '$translate', '$filter', 'growl', 'growlMessages', 'aside',
  function (
    $scope, AuctionConfig, AuctionUtils,
    $timeout, $http, $log, $cookies, $window,
    $rootScope, $location, $translate, $filter, growl, growlMessages, $aside
  ) {
    // init variables
    $scope.growlMessages = growlMessages;
    growlMessages.initDirective(0, 10);
    $scope.allow_bidding = true;
    $scope.bid = null;
    $rootScope.form = {};
    $rootScope.alerts = [];
    $scope.db = new PouchDB(AuctionConfig.remote_db);
    if ($translate.storage().get($translate.storageKey()) != "undefined"){
      $scope.lang = $translate.storage().get($translate.storageKey());
    } else {
      $translate.use(AuctionConfig.default_lang);
      $scope.lang = AuctionConfig.default_lang;
    }
    $scope.format_date = AuctionUtils.format_date;
    $scope.bidder_id = null;
    $scope.$on('kick_client', function(event, client_id, msg) {
      $log.debug('Kick client connection', client_id, msg);
      $scope.growlMessages.deleteMessage(msg);
      $http.post('./kickclient', {'client_id': client_id}).success(
        function (data) {
          $log.debug('disable connection', client_id, msg);
      })
    });
    $scope.start_subscribe = function (argument) {
      evtSrc = new EventSource(window.location.href.replace(window.location.search, '') + '/event_source');
      $scope.restart_retries_events = 5;
      evtSrc.addEventListener('ClientsList', function (e) {
        var data = angular.fromJson(e.data);
        $log.debug("New ClientsList: ", data);
        $scope.$apply(function () {
          var i;
          if (angular.isObject($scope.clients)) {
            for (i in data) {
              if (!(i in $scope.clients)) {
                growl.warning($filter('translate')('In the room came a new user') + ' (IP:' + data[i].ip + ')' +'<button type="button" ng-click="$emit(\'kick_client\', + \''+i+'\', message )" class="btn btn-link">' + $filter('translate')('prohibit connection') + '</button>', {
                  ttl: 30000,
                  disableCountDown: true
                });
              }
            }
          }
          $scope.clients = data;
        });
      }, false);
      evtSrc.addEventListener('Tick', function (e) {
        $scope.restart_retries_events = 5;
        var data = angular.fromJson(e.data);
        $log.debug("Tick: ", data);
      }, false);
      evtSrc.addEventListener('Identification', function (e) {
        var data = angular.fromJson(e.data);
        $log.debug("Identification: ", data);
        $scope.$apply(function () {
          $scope.bidder_id = data.bidder_id;
          $scope.client_id = data.client_id;
          $scope.return_url = data.return_url;
        })
      }, false);

      evtSrc.addEventListener('KickClient', function (e) {
        var data = angular.fromJson(e.data);
        $log.debug("You are must logout: ", data);
        window.location.replace(window.location.href + '/logout');
      }, false);
      evtSrc.addEventListener('Close', function (e) {
        $log.debug("You are must logout ");
        evtSrc.close();
      }, false);
      evtSrc.onerror = function (e) {
        $scope.restart_retries_events = $scope.restart_retries_events - 1;
        $log.debug("EventSource failed.", e);
        if($scope.restart_retries_events == 0){
          evtSrc.close();
          $log.debug("EventSource Stoped.", e);
        }
      };
    };
    $scope.changeLanguage = function (langKey) {
      $translate.use(langKey);
      $scope.lang = langKey;
    };
    // Bidding form msgs
    $scope.closeAlert = function (msg_id) {
      for (var i = 0; i < $rootScope.alerts.length; i++) {
        if ($rootScope.alerts[i].msg_id == msg_id) {
          $rootScope.alerts.splice(i, 1);
          return true;
        }
      }
    };
    $scope.auto_close_alert = function (msg_id) {
      $timeout(function () {
        $scope.closeAlert(msg_id);
      }, 4000);
    };
    $scope.get_round_number = function (pause_index) {
      return AuctionUtils.get_round_data(pause_index, $scope.auction_doc, $scope.Rounds);
    };
    $scope.show_bids_form = function (argument) {
      if ((angular.isNumber($scope.auction_doc.current_stage)) && ($scope.auction_doc.current_stage >= 0)) {
        if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'bids') && ($scope.auction_doc.stages[$scope.auction_doc.current_stage].bidder_id == $scope.bidder_id)) {
          return true;
        }
      }
      return false;
    };
    $scope.sync_times_with_server = function (start) {
      $http.get('/get_current_server_time').success(function (data) {
        $scope.last_sync = new Date(data);
        $rootScope.info_timer = AuctionUtils.prepare_info_timer_data($scope.last_sync, $scope.auction_doc, $scope.bidder_id, $scope.Rounds);
        $log.debug("Info timer data:", $rootScope.info_timer);
        $rootScope.progres_timer = AuctionUtils.prepare_progress_timer_data($scope.last_sync, $scope.auction_doc);
        $log.debug("Progres timer data:", $rootScope.progres_timer);

      });
    };
    $scope.post_bid = function () {
      if ($rootScope.form.BidsForm.$valid) {
        $http.post('./postbid', {
          'bid': $rootScope.form.bid,
          'bidder_id': $scope.bidder_id || bidder_id || "0"
        }).success(function (data) {
          var msg_id = '';
          if (data.status == 'failed') {
            for (var error_id in data.errors) {
              for (var i in data.errors[error_id]) {
                msg_id = Math.random();
                $rootScope.alerts.push({
                  msg_id: msg_id,
                  type: 'danger',
                  msg: data.errors[error_id][i]
                });
                $scope.auto_close_alert(msg_id);
              }
            }
          } else {
            if ($rootScope.form.bid <= ($scope.max_bid_amount() * 0.1)){
              msg_id = Math.random();
              $rootScope.alerts.push({
                msg_id: msg_id,
                type: 'warning',
                msg: 'Your bid appears too low'
              });
            }
            msg_id = Math.random();
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
    $scope.edit_bid = function () {
      $scope.allow_bidding = true;
    };

    $scope.max_bid_amount = function () {
      var amount = 0;
      if ((angular.isString($scope.bidder_id)) && (angular.isObject($scope.auction_doc)) && (angular.isObject($scope.auction_doc.stages[$scope.auction_doc.current_stage]))) {
        amount = $scope.auction_doc.stages[$scope.auction_doc.current_stage].amount - $scope.auction_doc.minimalStep.amount;
      }
      if (amount < 0){
        return 0;
      };
      return amount
    };
    $scope.calculate_minimal_bid_amount = function () {
      if ((angular.isObject($scope.auction_doc)) && (angular.isArray($scope.auction_doc.stages)) && (angular.isArray($scope.auction_doc.initial_bids))) {
        var bids = [];
        filter_func = function (item, index) {
          if (!angular.isUndefined(item.amount)) {
            bids.push(item.amount);
          }
        };
        $scope.auction_doc.stages.forEach(filter_func);
        $scope.auction_doc.initial_bids.forEach(filter_func);
        $scope.minimal_bid = bids.sort()[0];
      }
    };
    $scope.start_sync = function () {
      $scope.changes = $scope.db.changes({
        live: true,
        style: 'main_only',
        continuous: true,
        include_docs: true,
        doc_ids: [AuctionConfig.auction_doc_id],
        since: 0
      }).on('change', function (resp) {
        $log.debug('Change: ', resp);
        $scope.restart_retries = AuctionConfig.restart_retries;
        if (resp.id == AuctionConfig.auction_doc_id) {
          $scope.replace_document(resp.doc);
          if ($scope.auction_doc.current_stage == ($scope.auction_doc.stages.length - 1)) {
            $scope.changes.cancel();
          }
        }
      }).on('error', function (err) {
        $log.error('Changes error: ', err);
        $timeout(function () {
          growl.warning('Internet connection is lost. Attempt to restart after 1 sec', {
            ttl: 1000
          });
          $scope.restart_retries -= 1;
          if ($scope.restart_retries) {
            $log.debug('Start restart feed pooling...');
            $scope.restart_changes();
          } else {
            growl.error('Synchronization failed');
            $log.error('Restart synchronization not allowed.', AuctionConfig.restart_retries);
          }
        }, 1000);
      });
    };
    $scope.db.get(AuctionConfig.auction_doc_id, function (err, doc) {
      if (err) {
        $log.error('Error:', err);
        return 0;
      }
      $scope.start_subscribe();
      $scope.replace_document(doc);
      $scope.document_exists = true;
      $scope.scroll_to_stage();
      if ($scope.auction_doc.current_stage != ($scope.auction_doc.stages.length - 1)) {
        $scope.restart_retries = AuctionConfig.restart_retries;
        $scope.sync = $scope.start_sync();
      }
    });
    $scope.restart_changes = function () {
      $scope.changes.cancel();
      $timeout(function () {
        $scope.start_sync();
      }, 1000);
    };
    $scope.replace_document = function (new_doc) {
      $rootScope.$apply(function (argument) {
        if ((angular.isUndefined($scope.auction_doc)) || (new_doc.current_stage - $scope.auction_doc.current_stage === 0) || (new_doc.current_stage === -1)) {
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
    };
    $scope.calculate_rounds = function (argument) {
      $scope.Rounds = [];
      $scope.auction_doc.stages.forEach(function (item, index) {
        if (item.type == 'pause') {
          $scope.Rounds.push(index);
        }
      });

    };
    $scope.scroll_to_stage = function (argument) {
      AuctionUtils.scroll_to_stage($scope.auction_doc.current_stage);
    };
    $scope.array = function (int) {
      return new Array(int);
    };
    $scope.open_menu = function () {
      var modalInstance = $aside.open({
        templateUrl: 'templates/menu.html',
        controller: 'OffCanvasController',
        scope: $scope,
        size: 'lg'
      });
    };
  }
]);


angular.module('auction').controller('OffCanvasController', ['$scope', '$modalInstance', 
  function($scope, $modalInstance){
    $scope.allert = function () {
      console.log($scope);
      // body...
    }
    $scope.ok = function () {
      $modalInstance.close($scope.selected.item);
    };
    $scope.cancel = function () {
      $modalInstance.dismiss('cancel');
    };
  }
]);


angular.module('auction').directive('nghReplace', function($compile, $parse, $rootScope) {
    return {
      replace: true,
      link: function(scope, element, attr) {
        scope.$watch(attr.content, function() {
          element.html($parse(attr.content)(scope));
          $compile(element.contents())(scope);
        }, true);
      }
    }
  })


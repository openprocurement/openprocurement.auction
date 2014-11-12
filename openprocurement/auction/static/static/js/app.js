var app = angular.module('app', ['ui.bootstrap', 'pascalprecht.translate', 'timer']);
var db = {};
var bidder_id = "0"



app.constant('AuctionConfig', {
  dbname: 'auction',
  auction_doc_id: auction_doc_id,
  remote_db: db_url
});

app.controller('AuctionController', function(
  $scope, AuctionConfig,
  $timeout, $http, $log,
  $rootScope, $location, $translate, $filter
) {
  $scope.format_date = function (date, format) {
    return $filter('date')(date, $filter('translate')(format));
  };

  $scope.changeLanguage = function (langKey) {
    $translate.use(langKey);
  };
  $scope.alerts = [];
  $scope.bidder_id = null;
  $scope.allow_bidding = true;

  $scope.closeAlert = function(msg_id) {
    for (var i = 0; i < $scope.alerts.length; i++) {
      if ($scope.alerts[i].msg_id == msg_id) {
        $scope.alerts.splice(i, 1);
        return true;
      }
    };
  };

  db = $scope.db = new PouchDB(AuctionConfig.dbname);
  $scope.auction_doc = {
    "current_stage": null,

  }
  $scope.auto_close_alert = function(msg_id) {
    $timeout(function() {
      $scope.closeAlert(msg_id)
    }, 400000);
  }
  $scope.setuser = function(bidder_id) {
    $scope.bidder_id = bidder_id;
  }
  $scope.update_countdown_time = function(start_date, end_date) {
    $scope.interval = (end_date - start_date) / 1000;
    if ($scope.interval > 0) {
      $scope.$broadcast('timer-set-countdown', $scope.interval);
      $scope.$broadcast('timer-start');
    };
  }
  $scope.get_round_number = function(pause_index) {
    var pauses = [0];
    if($scope.auction_doc.stages){
      $scope.auction_doc.stages.forEach(function(item, index) {
        if (item.type == 'pause') {
          pauses.push(index);
        };
      })
      pauses.push($scope.auction_doc.stages.length - 1);
    }
    if (pause_index <= pauses[0]){
      return "-> 1"
    }
    for (var i in pauses) {
      if (pause_index < pauses[i]) {
        return $filter('translate')('Round #') + (parseInt(i) - 1).toString()
      }else if ((pause_index == pauses[i])&&(pause_index != $scope.auction_doc.stages.length - 1)){
        return (parseInt(i) - 1).toString() + "->" + (parseInt(i)).toString()
      }
    };
    return $filter('translate')('Finished') 
  }
  $scope.show_bids_form = function(argument) {
    if ((angular.isNumber($scope.auction_doc.current_stage)) && ($scope.auction_doc.current_stage >= 0)) {
      if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'bids') && ($scope.auction_doc.stages[$scope.auction_doc.current_stage].bidder_id == $scope.bidder_id)) {
        return true;
      } else if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'preliminary_bids')) {
        for (var i in $scope.auction_doc.initial_bids) {
          if ($scope.auction_doc.initial_bids[i].bidder_id == $scope.bidder_id) {
            return true;
          }
        }
      }
    }
    return false;
  }
  $scope.sync_countdown_time_with_server = function(start) {
    $http.get('/get_corrent_server_time').success(function(data) {
      $scope.last_sync = new Date(data);
      if (($scope.auction_doc) && ($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1])) {
        var end = new Date($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1]["start"]);
      } else if ($scope.auction_doc) {
        var end = new Date($scope.auction_doc.endDate);
      } else {
        var end = new Date();
      }
      $scope.update_countdown_time($scope.last_sync, end)
    });
  }
  $scope.post_bid = function() {
    if ($scope.BidsForm.$valid) {
      $http.post('/postbid', {
        'bid': $scope.bid,
        'bidder_id': $scope.bidder_id || bidder_id || "0"
      }).success(function(data) {
        if (data.status == 'failed') {
          for (var error_id in data.errors) {
            for (var i in data.errors[error_id]) {
              var msg_id = Math.random();
              $scope.alerts.push({
                msg_id: msg_id,
                type: 'danger',
                msg: data.errors[error_id][i]
              });
              $scope.auto_close_alert(msg_id);
            }
          }
        } else {
          var msg_id = Math.random();
          $scope.alerts.push({
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
  $scope.get_auction_data = function() {
    db.get(AuctionConfig.auction_doc_id, function(err, doc) {
      $log.debug("Get doc", doc);
      $rootScope.$apply(function(argument) {
        $scope.auction_doc = doc;
      });
    });
  }
  $scope.max_bid_amount = function() {
    if ((angular.isString($scope.bidder_id)) && (angular.isObject($scope.auction_doc))) {
      if ($scope.auction_doc.current_stage == 0) {
        for (var i = $scope.auction_doc.initial_bids.length - 1; i >= 0; i--) {
          if ($scope.auction_doc.initial_bids[i].bidder_id == $scope.bidder_id) {
            return $scope.auction_doc.initial_bids[i].amount - $scope.auction_doc.minimalStep.amount
          }
        };
      } else {
        return $scope.auction_doc.stages[$scope.auction_doc.current_stage].amount - $scope.auction_doc.minimalStep.amount
      }
    }
    return 0
  }
  $scope.start_sync = function() {
    $scope.replicate = PouchDB.replicate(AuctionConfig.remote_db, AuctionConfig.dbname, {
      live: true,
      doc_ids: [AuctionConfig.auction_doc_id]
    })
    $scope.changes = $scope.db.changes({
      live: true,
      continuous: true,
      include_docs: true,
      since: 'now',
      onChange: function(change) {
        $log.debug('onChanges:info - ', change);
        if (change.id == AuctionConfig.auction_doc_id) {
          $rootScope.$apply(function(argument) {
            if (($scope.auction_doc.current_stage == null) || (change.doc.current_stage - $scope.auction_doc.current_stage == 0) || (change.doc.current_stage == -1)) {
              $scope.auction_doc = change.doc;
              $scope.sync_countdown_time_with_server();
            } else {
              $scope.bid = null;
              $scope.allow_bidding = true;
              if (change.doc.stages[change.doc.current_stage]["start"]) {
                var start = new Date(change.doc.stages[change.doc.current_stage]["start"]);
              } else {
                var start = new Date();
              }
              if (change.doc.stages[change.doc.current_stage + 1]) {
                var end = new Date(change.doc.stages[change.doc.current_stage + 1]["start"]);
              } else {
                var end = new Date(change.doc.endDate)
              }
              $scope.update_countdown_time(start, end)
              $scope.auction_doc = change.doc;
            }
           
          });
        }
      }
    });
  };
  $scope.sync = $scope.start_sync();
  $scope.restart_changes = function() {
      $scope.replicate.cancel();
      $scope.changes.cancel();
      $scope.start_sync();
    }
    // $scope.get_auction_data();

});

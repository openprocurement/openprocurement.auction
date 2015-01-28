var auction_doc_id = 'test';
beforeEach(module('auction'));

describe('Unit: Testing Filter "formatnumber" - ', function() {
  it('formatnumber should format positive numbers', inject(function($filter) {
    expect($filter('formatnumber')(100000)).toEqual('100 000');
    expect($filter('formatnumber')(10000)).toEqual('10 000');
    expect($filter('formatnumber')(1000)).toEqual('1 000');
    expect($filter('formatnumber')(100)).toEqual('100');
    expect($filter('formatnumber')(10)).toEqual('10');
    expect($filter('formatnumber')(1)).toEqual('1');
  }));

  it('formatnumber should format nagative numbers', inject(function($filter) {
    expect($filter('formatnumber')(-100000)).toEqual('-100 000');
    expect($filter('formatnumber')(-10000)).toEqual('-10 000');
    expect($filter('formatnumber')(-1000)).toEqual('-1 000');
    expect($filter('formatnumber')(-100)).toEqual('-100');
    expect($filter('formatnumber')(-10)).toEqual('-10');
    expect($filter('formatnumber')(-1)).toEqual('-1');
  }));

  it('formatnumber should works with incorect values', inject(function($filter) {
    expect($filter('formatnumber')('string')).toEqual('');
    expect($filter('formatnumber')('')).toEqual($filter('number')('')); // '0' 
    expect($filter('formatnumber')({})).toEqual('');
    expect($filter('formatnumber')(true)).toEqual('1');
    expect($filter('formatnumber')(false)).toEqual('0');
  }));
});
class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transaction = []
        
    def new_block(self):
        # add a new block
        pass

    def new_transaction(self):
        # add a new transaction
        pass

    @staticmethod
    def hash(block):
        # hash a block
        pass

    @property
    def last_block(self):
        return self.chain[-1]

    def proof_of_work(self, last_proof):
        pass

